import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse

from app.dependencies import get_chat_orchestrator_service, get_course_service, get_current_user_id, get_session_material_store
from app.exceptions import CourseServiceError
from app.models import (
    CourseMaterial,
    CourseCreate,
    CourseMaterialCreate,
    CourseMaterialResponse,
    CourseMaterialsResponse,
    CourseResponse,
    CoursesResponse,
    MessageData,
    MessageResponse,
    PracticeChatData,
    PracticeChatRequest,
    PracticeChatResponse,
    PracticeHintData,
    PracticeHintRequest,
    PracticeHintResponse,
)
from app.services.course_service import ALLOWED_EXTENSIONS, CourseService
from app.services.chat_orchestrator_service import ChatOrchestratorService
from app.services.session_material_store import SessionMaterialStore

page_router = APIRouter(tags=["practice-pages"])
router = APIRouter(prefix="/practice", tags=["practice"])

_MAX_FILE_BYTES = 50 * 1024 * 1024


@page_router.get("/practice", include_in_schema=False)
def practice_upload_page() -> FileResponse:
    return FileResponse(
        Path(__file__).parent.parent.parent / "frontend" / "practiceupload" / "uploadpractice.html",
        media_type="text/html",
    )


@router.post("/courses", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
def create_practice_course(
    payload: CourseCreate,
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
) -> CourseResponse:
    data = course_service.create_course(user_id, payload)
    return CourseResponse(success=True, message="Practice course created successfully", data=data)


@router.get("/courses", response_model=CoursesResponse)
def list_practice_courses(
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
) -> CoursesResponse:
    data = course_service.list_courses(user_id)
    return CoursesResponse(success=True, message="Practice courses retrieved", data=data)


@router.get("/courses/{course_id}", response_model=CourseResponse)
def get_practice_course(
    course_id: str,
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
) -> CourseResponse:
    data = course_service.get_course(user_id, course_id)
    return CourseResponse(success=True, message="Practice course retrieved", data=data)


@router.post(
    "/courses/{course_id}/materials/text",
    response_model=CourseMaterialResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_practice_text_material(
    course_id: str,
    payload: CourseMaterialCreate,
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
    session_material_store: SessionMaterialStore = Depends(get_session_material_store),
) -> CourseMaterialResponse:
    data = course_service.add_text_material(user_id, course_id, payload)
    session_material_store.add_material(user_id, data)
    return CourseMaterialResponse(success=True, message="Practice text material uploaded", data=data)


@router.post(
    "/courses/{course_id}/materials/file",
    response_model=CourseMaterialResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_practice_file_material(
    course_id: str,
    file: UploadFile = File(..., description="Practice material upload"),
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
    session_material_store: SessionMaterialStore = Depends(get_session_material_store),
) -> CourseMaterialResponse:
    filename = file.filename or "upload"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise CourseServiceError(
            415,
            "UNSUPPORTED_FILE_TYPE",
            f"Extension '{ext}' is not allowed. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    file_bytes = file.file.read(_MAX_FILE_BYTES + 1)
    if len(file_bytes) > _MAX_FILE_BYTES:
        raise CourseServiceError(413, "FILE_TOO_LARGE", "File must be 50 MB or smaller")

    mime_type = file.content_type or "application/octet-stream"
    data = course_service.add_file_material(user_id, course_id, file_bytes, filename, mime_type)
    session_material_store.add_material(user_id, data)
    return CourseMaterialResponse(success=True, message=f"'{filename}' uploaded successfully", data=data)


@router.get("/courses/{course_id}/materials", response_model=CourseMaterialsResponse)
def list_practice_materials(
    course_id: str,
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
) -> CourseMaterialsResponse:
    data = course_service.list_materials(user_id, course_id)
    return CourseMaterialsResponse(success=True, message="Practice materials retrieved", data=data)


@router.get("/materials/session", response_model=CourseMaterialsResponse)
def list_session_practice_materials(
    user_id: str = Depends(get_current_user_id),
    session_material_store: SessionMaterialStore = Depends(get_session_material_store),
) -> CourseMaterialsResponse:
    data = session_material_store.list_materials(user_id)
    return CourseMaterialsResponse(success=True, message="Session materials retrieved", data=data)


@router.post("/chat", response_model=PracticeChatResponse)
def practice_chat(
    payload: PracticeChatRequest,
    user_id: str = Depends(get_current_user_id),
    chat_orchestrator: ChatOrchestratorService = Depends(get_chat_orchestrator_service),
) -> PracticeChatResponse:
    reply, _ = chat_orchestrator.generate_course_chat_reply(
        user_id=user_id,
        user_message=payload.message,
        course_id=payload.course_id,
        material_files=payload.material_files,
        problem_id=payload.problem_id,
        max_context_files=1,
    )

    return PracticeChatResponse(success=True, message="Reply generated", data=PracticeChatData(reply=reply))


@router.post("/hint", response_model=PracticeHintResponse)
def practice_hint(
    payload: PracticeHintRequest,
    user_id: str = Depends(get_current_user_id),
    chat_orchestrator: ChatOrchestratorService = Depends(get_chat_orchestrator_service),
) -> PracticeHintResponse:
    hint, _ = chat_orchestrator.generate_practice_hint(
        user_id=user_id,
        course_id=payload.course_id,
        material_files=payload.material_files,
        problem_id=payload.problem_id,
        max_context_files=1,
    )

    return PracticeHintResponse(success=True, message="Hint generated", data=PracticeHintData(hint=hint))


@router.get("/courses/{course_id}/materials/{material_id}/download")
def download_practice_material(
    course_id: str,
    material_id: str,
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
) -> RedirectResponse:
    materials = course_service.list_materials(user_id, course_id)
    material = next((m for m in materials if m.id == material_id), None)
    if not material:
        raise CourseServiceError(404, "MATERIAL_NOT_FOUND", "Material not found")
    if not material.storage_url:
        raise CourseServiceError(400, "NO_FILE", "This material has no downloadable file")

    return RedirectResponse(url=material.storage_url)


@router.post("/courses/{course_id}/past_problems/upload", response_model=MessageResponse)
def upload_practice_past_problems(
    course_id: str,
    question_file: list[UploadFile] = File(..., description="Practice material files (saved to question)"),
    answer_file: list[UploadFile] | None = File(default=None, description="Optional answer files (saved to answer)"),
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
    session_material_store: SessionMaterialStore = Depends(get_session_material_store),
) -> MessageResponse:
    if not question_file:
        raise CourseServiceError(400, "MISSING_QUESTION_FILES", "At least one material file is required")

    if len(question_file) != 1:
        raise CourseServiceError(400, "INVALID_QUESTION_FILE_COUNT", "Upload exactly one practice material file")

    answer_file = answer_file or []
    if len(answer_file) > 1:
        raise CourseServiceError(400, "INVALID_ANSWER_FILE_COUNT", "Upload at most one answer file")

    q_file = question_file[0]
    q_filename = q_file.filename or "question_upload"
    q_ext = os.path.splitext(q_filename)[1].lower()
    if q_ext not in ALLOWED_EXTENSIONS:
        raise CourseServiceError(
            415,
            "UNSUPPORTED_FILE_TYPE",
            f"Question extension '{q_ext}' is not allowed. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    q_bytes = q_file.file.read(_MAX_FILE_BYTES + 1)
    if len(q_bytes) > _MAX_FILE_BYTES:
        raise CourseServiceError(413, "FILE_TOO_LARGE", "Question file must be 50 MB or smaller")

    a_bytes = None
    a_filename = None
    a_mime = None
    if answer_file:
        a_file = answer_file[0]
        a_filename = a_file.filename or "answer_upload"
        a_ext = os.path.splitext(a_filename)[1].lower()
        if a_ext not in ALLOWED_EXTENSIONS:
            raise CourseServiceError(
                415,
                "UNSUPPORTED_FILE_TYPE",
                f"Answer extension '{a_ext}' is not allowed. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            )

        a_bytes = a_file.file.read(_MAX_FILE_BYTES + 1)
        if len(a_bytes) > _MAX_FILE_BYTES:
            raise CourseServiceError(413, "FILE_TOO_LARGE", "Answer file must be 50 MB or smaller")
        a_mime = a_file.content_type or "application/octet-stream"

    created_problem = course_service.add_practice_problem_file(
        user_id=user_id,
        course_id=course_id,
        question_bytes=q_bytes,
        question_filename=q_filename,
        question_mime_type=q_file.content_type or "application/octet-stream",
        answer_bytes=a_bytes,
        answer_filename=a_filename,
        answer_mime_type=a_mime,
    )

    # Keep practice viewer scoped to the latest upload session for this user.
    session_material_store.clear_materials(user_id)

    question_url = created_problem.get("question")
    if question_url:
        session_material_store.add_material(
            user_id,
            CourseMaterial(
                id=f"{created_problem.get('id', q_filename)}-question",
                course_id=course_id,
                user_id=user_id,
                is_text=False,
                filename=q_filename,
                mime_type=q_file.content_type or "application/octet-stream",
                storage_url=question_url,
                text_material=None,
                created_at=created_problem.get("created_at"),
            ),
        )

    answer_url = created_problem.get("answer")
    if answer_url:
        session_material_store.add_material(
            user_id,
            CourseMaterial(
                id=f"{created_problem.get('id', a_filename or 'answer')}-answer",
                course_id=course_id,
                user_id=user_id,
                is_text=False,
                filename=a_filename or "answer_upload",
                mime_type=a_mime or "application/octet-stream",
                storage_url=answer_url,
                text_material=None,
                created_at=created_problem.get("created_at"),
            ),
        )

    return MessageResponse(
        success=True,
        message="Uploaded 1 practice problem",
        data=MessageData(action="practice_past_problems_uploaded", problem_id=created_problem.get("id")),
    )