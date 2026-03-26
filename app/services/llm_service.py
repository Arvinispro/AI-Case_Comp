import os
import re
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, Field
from pypdf import PdfReader

from app.exceptions import AppError


class _StructuredScheduleItem(BaseModel):
    duration_minutes: int = Field(ge=1, le=720)
    activity_type: str
    activity: str = Field(min_length=1)


class _StructuredScheduleResponse(BaseModel):
    schedule_items: list[_StructuredScheduleItem] = Field(default_factory=list, max_length=100)


class LLMService:
    def __init__(self) -> None:
        env_path = Path(__file__).resolve().parents[2] / ".env"
        load_dotenv(dotenv_path=env_path, override=True)

        self.api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"

        if not self.api_key:
            raise AppError(500, "LLM_CONFIG_ERROR", "Missing GEMINI_API_KEY in environment")

        self.client = genai.Client(api_key=self.api_key)

    @staticmethod
    def _truncate_chars(value: str, max_chars: int) -> str:
        text = (value or "").strip()
        return text[:max_chars] if len(text) > max_chars else text

    @staticmethod
    def _limit_to_token_like_words(value: str, max_tokens: int) -> str:
        text = (value or "").strip()
        if not text:
            return ""
        chunks = text.split()
        if len(chunks) <= max_tokens:
            return text
        return " ".join(chunks[:max_tokens]).strip()

    @staticmethod
    def _detect_extension_from_url(url: str) -> str:
        path = urlparse(url).path.lower()
        if "." not in path:
            return ""
        return path.rsplit(".", 1)[-1]

    def extract_question_context(self, question_url: str | None) -> str | None:
        if not question_url:
            return None

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(question_url)
                response.raise_for_status()
                file_bytes = response.content
                content_type = (response.headers.get("content-type") or "").lower()
        except Exception:
            return None

        extension = self._detect_extension_from_url(question_url)
        is_pdf = "pdf" in content_type or extension == "pdf"
        is_text = content_type.startswith("text/") or extension in {"txt", "md"}

        if is_pdf:
            try:
                reader = PdfReader(BytesIO(file_bytes))
                pages: list[str] = []
                for page in reader.pages:
                    extracted = page.extract_text() or ""
                    if extracted.strip():
                        pages.append(extracted)
                if not pages:
                    return None
                return self._truncate_chars("\n\n".join(pages), 12000)
            except Exception:
                return None

        if is_text:
            for encoding in ("utf-8", "latin-1"):
                try:
                    return self._truncate_chars(file_bytes.decode(encoding), 12000)
                except Exception:
                    continue

        return None

    def _download_question_file(self, question_url: str | None) -> tuple[bytes, str, str] | None:
        if not question_url:
            return None

        file_bytes = None
        content_type = "application/octet-stream"
        for _ in range(3):
            try:
                with httpx.Client(timeout=45.0) as client:
                    response = client.get(question_url)
                    response.raise_for_status()
                    file_bytes = response.content
                    content_type = (response.headers.get("content-type") or "application/octet-stream").lower()
                    break
            except Exception:
                time.sleep(0.35)
                continue

        if file_bytes is None:
            return None

        extension = self._detect_extension_from_url(question_url)
        return file_bytes, content_type, extension

    def _build_file_part_from_url(self, file_url: str | None) -> genai_types.Part | None:
        downloaded = self._download_question_file(file_url)
        if downloaded is None:
            return None

        file_bytes, content_type, extension = downloaded
        normalized_mime = self._normalize_mime_type(content_type, extension)

        try:
            return genai_types.Part.from_bytes(data=file_bytes, mime_type=normalized_mime)
        except Exception:
            return None

    @staticmethod
    def _normalize_mime_type(content_type: str, extension: str) -> str:
        lowered = (content_type or "").lower().strip()
        if lowered and lowered != "application/octet-stream":
            return lowered

        ext = (extension or "").lower().lstrip(".")
        ext_to_mime = {
            "pdf": "application/pdf",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "gif": "image/gif",
            "webp": "image/webp",
            "txt": "text/plain",
            "md": "text/markdown",
        }
        return ext_to_mime.get(ext, "application/octet-stream")

    @staticmethod
    def _to_readable_math(text: str) -> str:
        result = (text or "").strip()
        if not result:
            return result

        # Remove common LaTeX math delimiters.
        result = result.replace("\\[", "").replace("\\]", "")
        result = result.replace("\\(", "").replace("\\)", "")
        result = result.replace("$$", "")
        result = result.replace("$", "")

        # Fractions and roots.
        result = re.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1) divided by (\2)", result)
        result = re.sub(r"\\sqrt\s*\{([^{}]+)\}", r"square root of (\1)", result)

        # Exponents like x^{2} -> x to the power of 2.
        result = re.sub(r"\^\{([^{}]+)\}", r" to the power of \1", result)
        result = re.sub(r"\^([A-Za-z0-9]+)", r" to the power of \1", result)

        symbol_map = {
            r"\\times": " multiplied by ",
            r"\\cdot": " multiplied by ",
            r"\\div": " divided by ",
            r"\\pm": " plus or minus ",
            r"\\mp": " minus or plus ",
            r"\\leq": " less than or equal to ",
            r"\\geq": " greater than or equal to ",
            r"\\neq": " not equal to ",
            r"\\approx": " approximately ",
            r"\\pi": " pi ",
            r"\\theta": " theta ",
            r"\\alpha": " alpha ",
            r"\\beta": " beta ",
            r"\\gamma": " gamma ",
            r"\\Delta": " delta ",
            r"\\sum": " sum ",
            r"\\int": " integral ",
        }
        for latex, readable in symbol_map.items():
            result = re.sub(latex, readable, result)

        # Superscript numerals sometimes appear in plain unicode.
        result = (
            result.replace("²", "^2")
            .replace("³", "^3")
            .replace("⁴", "^4")
            .replace("⁵", "^5")
        )

        # Normalize whitespace after replacements.
        result = re.sub(r"\s+", " ", result).strip()
        return result

    @staticmethod
    def _friendly_llm_error(exc: Exception) -> str:
        message = str(exc).lower()
        if "429" in message or "resource_exhausted" in message or "quota" in message:
            return "Tutor is temporarily rate-limited. Please wait a moment and try again."
        if "401" in message or "403" in message or "api key" in message:
            return "Tutor configuration error. Please contact support."
        return "Tutor service is temporarily unavailable. Please try again shortly."

    @staticmethod
    def _is_rate_limited_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "429" in message or "resource_exhausted" in message or "quota" in message

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        return {token for token in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(token) > 1}

    def _fallback_reply_from_history(self, user_message: str, history: list[dict[str, str]]) -> str | None:
        best_answer = self.find_relevant_history_answer(user_message, history)
        if not best_answer:
            return None

        return (
            "I am currently rate-limited, but from our previous course conversation: "
            f"{best_answer}"
        )

    def find_relevant_history_answer(self, user_message: str, history: list[dict[str, str]]) -> str | None:
        user_tokens = self._tokenize(user_message)
        if not user_tokens or not history:
            return None

        best_score = 0
        best_answer = None
        for idx, item in enumerate(history):
            role = str(item.get("role", "")).strip().lower()
            if role != "user":
                continue

            content = str(item.get("content", "")).strip()
            if not content:
                continue

            overlap = len(user_tokens.intersection(self._tokenize(content)))
            if overlap <= best_score:
                continue

            # Prefer the immediate assistant/tutor response after the matched user turn.
            answer = None
            if idx + 1 < len(history):
                next_item = history[idx + 1]
                next_role = str(next_item.get("role", "")).strip().lower()
                next_content = str(next_item.get("content", "")).strip()
                if next_role in {"ai", "assistant", "tutor"} and next_content:
                    answer = next_content

            if answer:
                best_score = overlap
                best_answer = answer

        return best_answer

    @staticmethod
    def _response_to_structured_schedule(response) -> _StructuredScheduleResponse | None:
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, _StructuredScheduleResponse):
            return parsed

        if isinstance(parsed, dict):
            try:
                return _StructuredScheduleResponse.model_validate(parsed)
            except Exception:
                return None

        raw_text = str(getattr(response, "text", "") or "").strip()
        if not raw_text:
            return None

        try:
            return _StructuredScheduleResponse.model_validate_json(raw_text)
        except Exception:
            return None

    @staticmethod
    def _normalize_schedule_items(raw_items: list[dict]) -> list[dict[str, str | int]]:
        normalized: list[dict[str, str | int]] = []
        allowed_types = {"work", "break", "quiz"}

        for item in raw_items:
            duration_raw = item.get("duration_minutes") if isinstance(item, dict) else None
            activity_type = str(item.get("activity_type") if isinstance(item, dict) else "").strip().lower()
            activity_text = str(item.get("activity") if isinstance(item, dict) else "").strip()

            try:
                duration_minutes = int(duration_raw)
            except Exception:
                continue

            if duration_minutes <= 0:
                continue
            if activity_type not in allowed_types:
                continue
            if not activity_text:
                continue

            if activity_type == "quiz":
                activity_text = LLMService._normalize_quiz_topics(activity_text)

            normalized.append(
                {
                    "duration_minutes": duration_minutes,
                    "activity_type": activity_type,
                    "activity": activity_text,
                }
            )

        return normalized

    @staticmethod
    def _fallback_study_schedule(duration_minutes: int, materials: list[dict[str, str]]) -> list[dict[str, str | int]]:
        total = max(1, int(duration_minutes))
        break_minutes = 10 if total >= 45 else (5 if total >= 20 else 0)
        quiz_minutes = max(5, round(total * 0.2))
        if break_minutes + quiz_minutes >= total:
            break_minutes = 0 if total < 20 else min(5, max(0, total - 10))
            quiz_minutes = max(5, total - break_minutes - max(5, total // 2))

        work_minutes = max(5, total - break_minutes - quiz_minutes)

        sections: list[str] = []
        for idx, material in enumerate(materials, start=1):
            title = str(material.get("filename") or f"material {idx}").strip()
            summary = str(material.get("section_summary") or "").strip()
            refs = LLMService._extract_reference_hints(summary)
            ref_suffix = f" ({', '.join(refs[:3])})" if refs else ""
            if summary:
                sections.append(f"{title}{ref_suffix}: {summary}")
            else:
                sections.append(f"{title}: review section {idx}")

        if not sections:
            sections = ["uploaded materials: review key sections and definitions"]

        work_activity = f"read {sections[0]}"
        quiz_topic = LLMService._normalize_quiz_topics(sections[-1])

        schedule: list[dict[str, str | int]] = [
            {
                "duration_minutes": work_minutes,
                "activity_type": "work",
                "activity": work_activity,
            }
        ]
        if break_minutes > 0:
            schedule.append(
                {
                    "duration_minutes": break_minutes,
                    "activity_type": "break",
                    "activity": "short rest and hydration",
                }
            )
        schedule.append(
            {
                "duration_minutes": quiz_minutes,
                "activity_type": "quiz",
                "activity": quiz_topic,
            }
        )
        return schedule

    @staticmethod
    def _extract_reference_hints(text: str) -> list[str]:
        raw = (text or "").strip()
        if not raw:
            return []

        candidates: list[str] = []
        patterns = [
            r"\bpages?\s+\d+(?:\s*[-–]\s*\d+)?\b",
            r"\bsection\s+\d+(?:\.\d+)?\b",
            r"\bchapter\s+\d+(?:\.\d+)?\b",
            r"\bunit\s+\d+(?:\.\d+)?\b",
            r"\bmodule\s+\d+(?:\.\d+)?\b",
        ]
        for pattern in patterns:
            candidates.extend(re.findall(pattern, raw, flags=re.IGNORECASE))

        unique: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            normalized = re.sub(r"\s+", " ", item).strip().lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(normalized)

        return unique[:8]

    @staticmethod
    def _normalize_quiz_topics(text: str) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            return "core concepts"

        cleaned = re.sub(r"^(quiz|quiz yourself|test yourself|questions?)\s*(on|about)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .:-")

        parts = re.split(r"\n|;|\||,", cleaned)
        topics: list[str] = []
        for part in parts:
            topic = re.sub(r"^[\-•\*\d\.)\s]+", "", (part or "").strip())
            topic = topic.strip(" .")
            if not topic:
                continue
            if any(existing.lower() == topic.lower() for existing in topics):
                continue
            topics.append(topic)

        if not topics:
            return "core concepts"

        return ", ".join(topics)

    def generate_study_schedule(
        self,
        duration_minutes: int,
        learning_preferences: list[str] | None,
        materials: list[dict[str, str]],
        material_urls: list[str] | None = None,
    ) -> list[dict[str, str | int]]:
        safe_duration = max(1, int(duration_minutes))
        cleaned_preferences = [
            str(item).strip()
            for item in (learning_preferences or [])
            if str(item).strip()
        ]
        preference_block = (
            "\n".join([f"- {item}" for item in cleaned_preferences])
            if cleaned_preferences
            else "- No explicit preference provided"
        )

        structure_hints: list[str] = []
        if materials:
            material_lines: list[str] = []
            for idx, material in enumerate(materials, start=1):
                filename = str(material.get("filename") or f"Material {idx}").strip()
                summary = str(material.get("section_summary") or "").strip()
                clipped_summary = summary[:1200] if len(summary) > 1200 else summary
                refs = self._extract_reference_hints(clipped_summary)
                if refs:
                    structure_hints.append(f"{filename}: {', '.join(refs)}")
                material_lines.append(
                    f"{idx}. Filename: {filename}\n"
                    f"   Section summary: {clipped_summary or 'No extractable text summary'}"
                )
            materials_block = "\n".join(material_lines)
        else:
            materials_block = "No materials were provided."

        instruction = (
            "You are a study scheduling agent. "
            "Create a schedule to learn all uploaded materials within the total study time. "
            "You MUST tailor the plan to the learning preference.\n\n"
            "Hard rules:\n"
            "1) Output valid JSON matching the response schema.\n"
            "2) Use `schedule_items`, where each item has: duration_minutes, activity_type, activity.\n"
            "3) Use only the three activity types exactly: work, break, quiz.\n"
            "4) Read attached files and use their real content/structure (pages, sections, headings) when planning.\n"
            "4a) Work activities must reference concrete slices, e.g. 'Material A: read pages 1-2' or 'Section 3.1'.\n"
            "4a) For quiz rows, activity must be ONLY a plain comma-separated list of quiz topics.\n"
            "4b) For quiz rows, do NOT include verbs/instructions like 'quiz', 'test', 'review', or full sentences.\n"
            "4c) Quiz topics should include explicit section/page references when available, e.g. 'section 1, section 5'.\n"
            "5) Total time should sum to approximately the requested duration.\n"
            "6) Keep `duration_minutes` as integer minutes.\n\n"
            "Few-shot examples (style guide):\n"
            "Example A input: 60 minutes, preference='visual learner', materials mention pages 1-6 and section 2.\n"
            "Example A output JSON:\n"
            "{\"schedule_items\":["
            "{\"duration_minutes\":25,\"activity_type\":\"work\",\"activity\":\"Material 1: read pages 1-2\"},"
            "{\"duration_minutes\":20,\"activity_type\":\"work\",\"activity\":\"Material 1: read pages 3-4, section 2\"},"
            "{\"duration_minutes\":5,\"activity_type\":\"break\",\"activity\":\"short rest and hydration\"},"
            "{\"duration_minutes\":10,\"activity_type\":\"quiz\",\"activity\":\"page 1 definitions, page 4 diagrams, section 2 key ideas\"}]}\n\n"
            "Example B input: 35 minutes, preference='active recall', materials mention section 1, section 5, chapter 3.\n"
            "Example B output JSON:\n"
            "{\"schedule_items\":["
            "{\"duration_minutes\":15,\"activity_type\":\"work\",\"activity\":\"Material 2: read section 1\"},"
            "{\"duration_minutes\":10,\"activity_type\":\"work\",\"activity\":\"Material 2: read chapter 3\"},"
            "{\"duration_minutes\":10,\"activity_type\":\"quiz\",\"activity\":\"section 1, section 5, chapter 3\"}]}\n\n"
            "Follow the pattern above, but adapt to the real attached files and summaries in this request.\n\n"
            f"Requested total duration: {safe_duration} minutes\n"
            "Learning preferences:\n"
            f"{preference_block}\n"
            "Detected structure hints (best-effort):\n"
            f"{chr(10).join(f'- {hint}' for hint in structure_hints) if structure_hints else '- No explicit page/section hints extracted'}\n"
            "Materials and section summaries:\n"
            f"{materials_block}"
        )

        unique_urls: list[str] = []
        seen_urls: set[str] = set()
        for raw_url in material_urls or []:
            url = str(raw_url or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            unique_urls.append(url)

        material_parts: list[genai_types.Part] = []
        for url in unique_urls[:4]:
            part = self._build_file_part_from_url(url)
            if part is not None:
                material_parts.append(part)

        contents_payload: list[str | genai_types.Part] = [instruction]
        if material_parts:
            contents_payload.extend(material_parts)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents_payload,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_StructuredScheduleResponse,
                ),
            )
            structured = self._response_to_structured_schedule(response)
            if structured is not None:
                raw_items = [item.model_dump() for item in structured.schedule_items]
                normalized = self._normalize_schedule_items(raw_items)
                if normalized:
                    return normalized
        except Exception:
            pass

        return self._fallback_study_schedule(safe_duration, materials)

    def generate_practice_reply(
        self,
        user_message: str,
        material_files: list[str] | None = None,
        course_material_urls: list[str] | None = None,
        learning_preferences: list[str] | None = None,
        question_context: str | None = None,
        question_url: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        files = material_files or []
        history = conversation_history or []
        cleaned_preferences = [
            str(item).strip()
            for item in (learning_preferences or [])
            if str(item).strip()
        ]
        preference_section = (
            "\n".join([f"- {item}" for item in cleaned_preferences])
            if cleaned_preferences
            else "- No explicit preference provided"
        )
        files_section = "\n".join([f"- {name}" for name in files]) if files else "- No material filenames provided"
        context_section = question_context or (
            "Text extraction unavailable; rely on attached file content if present."
            if question_url
            else "No question file linked."
        )

        # Include the most recent turns so the tutor can answer follow-ups across sessions in the same course.
        recent_turns = history[-24:]
        history_lines: list[str] = []
        for item in recent_turns:
            role = str(item.get("role", "")).strip().lower()
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            label = "User" if role == "user" else "Tutor"
            history_lines.append(f"{label}: {content}")
        history_section = "\n".join(history_lines) if history_lines else "- No prior course conversation found"

        instruction = (
            "You are a concise, helpful AI tutor in a practice mode interface. "
            "Explain clearly, show steps when helpful, and stay focused on the asked question.\n"
            "Tailor tone and explanation style to the user's learning preferences.\n"
            "If the user asks a math question, answer as a math tutor with math reasoning only.\n"
            "Do not switch domains (for example, to commerce/business) unless the user explicitly asks for that.\n"
            "Do not use LaTeX notation in your final answer; use plain readable words and symbols only.\n"
            "If you are uncertain, say so clearly and show the best attempt instead of guessing confidently.\n"
            "If a file is attached, do not ask the user to paste the question text; use the file directly.\n"
            "Do not invent details not supported by the attached file or extracted text.\n\n"
            "Learning preferences for this user:\n"
            f"{preference_section}\n\n"
            "Prior saved conversation for this course (across sessions):\n"
            f"{history_section}\n\n"
            "Available material filenames from the user session:\n"
            f"{files_section}\n\n"
            "Extracted question file content (best-effort):\n"
            f"{context_section}\n\n"
            "If an attached file is present, treat it as the source of truth over extracted text. "
            "Keep the response under 180 words unless the user asks for detail."
        )

        response = None
        has_extracted_context = bool((question_context or "").strip())
        file_grounding_attempted = False

        unique_urls: list[str] = []
        seen_urls: set[str] = set()
        for raw_url in course_material_urls or []:
            url = str(raw_url or "").strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            unique_urls.append(url)

        material_parts: list[genai_types.Part] = []
        for url in unique_urls[:4]:
            part = self._build_file_part_from_url(url)
            if part is not None:
                material_parts.append(part)
                file_grounding_attempted = True

        # Quota optimization: only use multimodal file call when extracted text is unavailable.
        if question_url and not has_extracted_context and question_url not in seen_urls:
            downloaded = self._download_question_file(question_url)
            if downloaded is not None:
                file_grounding_attempted = True
                file_bytes, content_type, extension = downloaded
                normalized_mime = self._normalize_mime_type(content_type, extension)

                try:
                    material_parts.append(genai_types.Part.from_bytes(data=file_bytes, mime_type=normalized_mime))
                except genai_errors.APIError as exc:
                    if self._is_rate_limited_error(exc):
                        history_fallback = self._fallback_reply_from_history(user_message, history)
                        if history_fallback:
                            return history_fallback
                    return self._friendly_llm_error(exc)
                except Exception as exc:
                    return self._friendly_llm_error(exc)

        if response is None and material_parts:
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[instruction, *material_parts, f"User message: {user_message}"],
                )
            except genai_errors.APIError as exc:
                if self._is_rate_limited_error(exc):
                    history_fallback = self._fallback_reply_from_history(user_message, history)
                    if history_fallback:
                        return history_fallback
                return self._friendly_llm_error(exc)
            except Exception as exc:
                return self._friendly_llm_error(exc)

        if response is None:
            if question_url and file_grounding_attempted and not has_extracted_context:
                return (
                    "I could not reliably read the attached problem file this time. "
                    "Please re-upload a clear PDF/image and ask again."
                )

            # If a file URL exists but we could neither download nor extract content, avoid ungrounded answers.
            if question_url and not file_grounding_attempted and not has_extracted_context:
                return (
                    "I could not access the attached problem file right now. "
                    "Please try again or re-upload the file."
                )

            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=f"{instruction}\n\nUser message: {user_message}",
                )
            except genai_errors.APIError as exc:
                if self._is_rate_limited_error(exc):
                    history_fallback = self._fallback_reply_from_history(user_message, history)
                    if history_fallback:
                        return history_fallback
                return self._friendly_llm_error(exc)
            except Exception as exc:
                return self._friendly_llm_error(exc)

        reply = getattr(response, "text", None)
        if reply and str(reply).strip():
            return self._to_readable_math(str(reply))

        return "I could not generate a response right now. Please try again."

    def generate_practice_hint(
        self,
        user_message: str,
        learning_preferences: list[str] | None = None,
        question_context: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        cleaned_preferences = [
            str(item).strip()
            for item in (learning_preferences or [])
            if str(item).strip()
        ]
        preference_section = (
            "\n".join([f"- {item}" for item in cleaned_preferences])
            if cleaned_preferences
            else "- No explicit preference provided"
        )

        history = conversation_history or []
        recent_turns = history[-12:]
        history_lines: list[str] = []
        for item in recent_turns:
            role = str(item.get("role", "")).strip().lower()
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            label = "User" if role == "user" else "Tutor"
            history_lines.append(f"{label}: {content}")
        history_section = "\n".join(history_lines) if history_lines else "- No prior conversation found"

        context_section = question_context or "No extracted question content available."

        instruction = (
            "You are a math practice tutor. Give one short guiding hint only, not the final solution.\n"
            "Hint constraints:\n"
            "- Maximum 50 tokens.\n"
            "- One or two short sentences.\n"
            "- Focus on the next step the learner should try.\n"
            "- Do not reveal the full derivation or final answer.\n"
            "- Keep wording simple and direct.\n\n"
            "Learning preferences:\n"
            f"{preference_section}\n\n"
            "Recent conversation:\n"
            f"{history_section}\n\n"
            "Question context (best effort):\n"
            f"{context_section}\n\n"
            f"User message: {user_message}"
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=instruction,
                config=genai_types.GenerateContentConfig(max_output_tokens=50),
            )
        except genai_errors.APIError as exc:
            return self._friendly_llm_error(exc)
        except Exception as exc:
            return self._friendly_llm_error(exc)

        hint = getattr(response, "text", None)
        if hint and str(hint).strip():
            clean_hint = self._to_readable_math(str(hint))
            return self._limit_to_token_like_words(clean_hint, 50)

        return "Try isolating what is asked, then compute one small step before moving on."
