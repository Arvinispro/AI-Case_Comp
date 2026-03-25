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
from pypdf import PdfReader

from app.exceptions import AppError


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

    def generate_practice_reply(
        self,
        user_message: str,
        material_files: list[str] | None = None,
        question_context: str | None = None,
        question_url: str | None = None,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        files = material_files or []
        history = conversation_history or []
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
            "If the user asks a math question, answer as a math tutor with math reasoning only.\n"
            "Do not switch domains (for example, to commerce/business) unless the user explicitly asks for that.\n"
            "Do not use LaTeX notation in your final answer; use plain readable words and symbols only.\n"
            "If you are uncertain, say so clearly and show the best attempt instead of guessing confidently.\n"
            "If a file is attached, do not ask the user to paste the question text; use the file directly.\n"
            "Do not invent details not supported by the attached file or extracted text.\n\n"
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

        # Quota optimization: only use multimodal file call when extracted text is unavailable.
        if question_url and not has_extracted_context:
            downloaded = self._download_question_file(question_url)
            if downloaded is not None:
                file_grounding_attempted = True
                file_bytes, content_type, extension = downloaded
                normalized_mime = self._normalize_mime_type(content_type, extension)

                try:
                    file_part = genai_types.Part.from_bytes(data=file_bytes, mime_type=normalized_mime)
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=[instruction, file_part, f"User message: {user_message}"],
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
