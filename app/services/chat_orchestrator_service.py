from app.services.course_service import CourseService
from app.services.llm_service import LLMService
from app.services.session_material_store import SessionMaterialStore
from app.services.session_schedule_store import SessionScheduleStore


class ChatOrchestratorService:
    def __init__(
        self,
        course_service: CourseService,
        llm_service: LLMService,
        session_material_store: SessionMaterialStore,
        session_schedule_store: SessionScheduleStore,
    ) -> None:
        self.course_service = course_service
        self.llm_service = llm_service
        self.session_material_store = session_material_store
        self.session_schedule_store = session_schedule_store

    @staticmethod
    def _pick_session_materials(session_materials, material_files: list[str] | None):
        wanted = {name.strip().lower() for name in (material_files or []) if name and name.strip()}
        if wanted:
            return [
                item
                for item in session_materials
                if item.storage_url and item.filename and item.filename.strip().lower() in wanted
            ]
        return [item for item in session_materials if item.storage_url]

    @staticmethod
    def _is_question_or_request(message: str) -> bool:
        text = (message or "").strip().lower()
        if not text:
            return False

        if "?" in text:
            return True

        request_prefixes = (
            "what",
            "why",
            "how",
            "when",
            "where",
            "who",
            "which",
            "can you",
            "could you",
            "would you",
            "do ",
            "does ",
            "did ",
            "is ",
            "are ",
            "am ",
            "please",
            "explain",
            "solve",
            "help me",
            "find",
            "tell me",
            "show me",
        )
        return any(text.startswith(prefix) for prefix in request_prefixes)

    def generate_course_chat_reply(
        self,
        user_id: str,
        user_message: str,
        course_id: str | None,
        material_files: list[str] | None = None,
        problem_id: str | None = None,
        max_context_files: int = 1,
    ) -> tuple[str, str | None]:
        question_url = None
        question_context = None
        course_material_urls: list[str] = []
        learning_preferences = self.course_service.get_user_learning_preferences(user_id)
        files_for_prompt = material_files or []
        resolved_course_id = course_id

        if not self._is_question_or_request(user_message):
            reply = "Got it. I noted that."
            if resolved_course_id:
                self.course_service.append_practice_llm_conversation(
                    user_id=user_id,
                    course_id=resolved_course_id,
                    user_message=user_message,
                    ai_response=reply,
                )
            return reply, resolved_course_id

        candidate_materials = []
        if problem_id:
            problem = self.course_service.get_practice_problem(user_id=user_id, problem_id=problem_id)
            resolved_course_id = problem.get("course_id") or resolved_course_id
            question_url = problem.get("question")
            files_for_prompt = []
        else:
            session_materials = self.session_material_store.list_materials(user_id)
            candidate_materials = self._pick_session_materials(session_materials, material_files)
            if candidate_materials:
                question_url = candidate_materials[0].storage_url
                course_material_urls = [
                    item.storage_url
                    for item in candidate_materials[:max_context_files]
                    if item.storage_url
                ]
                files_for_prompt = []

        conversation_history: list[dict[str, str]] = []
        if resolved_course_id:
            conversation_history = self.course_service.get_course_llm_conversation(
                user_id=user_id,
                course_id=resolved_course_id,
            )

        recalled_answer = self.llm_service.find_relevant_history_answer(user_message, conversation_history)
        if recalled_answer:
            if resolved_course_id:
                self.course_service.append_practice_llm_conversation(
                    user_id=user_id,
                    course_id=resolved_course_id,
                    user_message=user_message,
                    ai_response=recalled_answer,
                )
            return recalled_answer, resolved_course_id

        if question_url:
            if not problem_id and candidate_materials and max_context_files > 1:
                context_parts: list[str] = []
                for material in candidate_materials[:max_context_files]:
                    part = self.llm_service.extract_question_context(material.storage_url)
                    if part:
                        context_parts.append(part)
                if context_parts:
                    question_context = "\n\n".join(context_parts)[:18000]
            else:
                question_context = self.llm_service.extract_question_context(question_url)

        reply = self.llm_service.generate_practice_reply(
            user_message=user_message,
            material_files=files_for_prompt,
            course_material_urls=course_material_urls,
            learning_preferences=learning_preferences,
            question_context=question_context,
            question_url=question_url,
            conversation_history=conversation_history,
        )

        if resolved_course_id:
            self.course_service.append_practice_llm_conversation(
                user_id=user_id,
                course_id=resolved_course_id,
                user_message=user_message,
                ai_response=reply,
            )

        return reply, resolved_course_id

    def generate_practice_hint(
        self,
        user_id: str,
        course_id: str | None,
        material_files: list[str] | None = None,
        problem_id: str | None = None,
        max_context_files: int = 1,
    ) -> tuple[str, str | None]:
        question_url = None
        question_context = None
        resolved_course_id = course_id
        learning_preferences = self.course_service.get_user_learning_preferences(user_id)

        candidate_materials = []
        if problem_id:
            problem = self.course_service.get_practice_problem(user_id=user_id, problem_id=problem_id)
            resolved_course_id = problem.get("course_id") or resolved_course_id
            question_url = problem.get("question")
        else:
            session_materials = self.session_material_store.list_materials(user_id)
            candidate_materials = self._pick_session_materials(session_materials, material_files)
            if candidate_materials:
                question_url = candidate_materials[0].storage_url

        conversation_history: list[dict[str, str]] = []
        if resolved_course_id:
            conversation_history = self.course_service.get_course_llm_conversation(
                user_id=user_id,
                course_id=resolved_course_id,
            )

        latest_user_message = "Give me a hint."
        for item in reversed(conversation_history):
            if str(item.get("role", "")).strip().lower() == "user":
                content = str(item.get("content", "")).strip()
                if content:
                    latest_user_message = content
                    break

        if question_url:
            if not problem_id and candidate_materials and max_context_files > 1:
                context_parts: list[str] = []
                for material in candidate_materials[:max_context_files]:
                    part = self.llm_service.extract_question_context(material.storage_url)
                    if part:
                        context_parts.append(part)
                if context_parts:
                    question_context = "\n\n".join(context_parts)[:18000]
            else:
                question_context = self.llm_service.extract_question_context(question_url)

        hint = self.llm_service.generate_practice_hint(
            user_message=latest_user_message,
            learning_preferences=learning_preferences,
            question_context=question_context,
            conversation_history=conversation_history,
        )

        if resolved_course_id:
            self.course_service.append_practice_llm_conversation(
                user_id=user_id,
                course_id=resolved_course_id,
                user_message="[Hint request]",
                ai_response=hint,
            )

        return hint, resolved_course_id

    def generate_study_schedule(
        self,
        user_id: str,
        duration_minutes: int,
        course_id: str | None,
        material_files: list[str] | None = None,
        max_context_files: int = 8,
    ) -> dict:
        learning_preferences = self.course_service.get_user_learning_preferences(user_id)

        session_materials = self.session_material_store.list_materials(user_id)
        selected_materials = self._pick_session_materials(session_materials, material_files)

        materials_for_schedule: list[dict[str, str]] = []
        material_urls_for_schedule: list[str] = []
        for item in selected_materials[:max_context_files]:
            filename = (item.filename or "").strip() or "Untitled material"
            summary = ""

            if item.text_material:
                summary = (item.text_material or "").strip()
            elif item.storage_url:
                extracted = self.llm_service.extract_question_context(item.storage_url)
                if extracted:
                    summary = extracted.strip()

            if len(summary) > 1800:
                summary = summary[:1800]

            materials_for_schedule.append(
                {
                    "filename": filename,
                    "section_summary": summary,
                }
            )
            if item.storage_url:
                material_urls_for_schedule.append(item.storage_url)

        schedule_items = self.llm_service.generate_study_schedule(
            duration_minutes=duration_minutes,
            learning_preferences=learning_preferences,
            materials=materials_for_schedule,
            material_urls=material_urls_for_schedule,
        )

        payload = {
            "schedule_items": schedule_items,
            "learning_preferences": learning_preferences,
            "duration_minutes": duration_minutes,
            "material_files": [m.get("filename") for m in materials_for_schedule if m.get("filename")],
            "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "course_id": course_id,
        }
        self.session_schedule_store.set_latest_schedule(user_id, payload)
        return payload
