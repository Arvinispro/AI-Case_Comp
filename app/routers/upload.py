from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import RedirectResponse

from app.dependencies import get_course_service, get_current_user_id
from app.exceptions import CourseServiceError
from app.models import (
    CourseMaterialCreate,
    CourseMaterialResponse,
    CourseMaterialsResponse,
    CourseCreate,
    CourseResponse,
    CoursesResponse,
)
from app.services.course_service import ALLOWED_EXTENSIONS, CourseService

router = APIRouter(prefix="/courses", tags=["courses"])

_MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB


# ── courses table ─────────────────────────────────────────────────────────────

@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
) -> CourseResponse:
    """Create a new course (inserted into the `courses` table)."""
    data = course_service.create_course(user_id, payload)
    return CourseResponse(success=True, message="Course created successfully", data=data)


@router.get("", response_model=CoursesResponse)
def list_courses(
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
) -> CoursesResponse:
    """List all courses belonging to the authenticated user."""
    data = course_service.list_courses(user_id)
    return CoursesResponse(success=True, message="Courses retrieved", data=data)


@router.get("/{course_id}", response_model=CourseResponse)
def get_course(
    course_id: str,
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
) -> CourseResponse:
    """Fetch a single course by id."""
    data = course_service.get_course(user_id, course_id)
    return CourseResponse(success=True, message="Course retrieved", data=data)


# ── course_materials table ────────────────────────────────────────────────────

@router.post(
    "/{course_id}/materials/text",
    response_model=CourseMaterialResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_text_material(
    course_id: str,
    payload: CourseMaterialCreate,
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
) -> CourseMaterialResponse:
    """Save a plain-text study material into `course_materials`."""
    data = course_service.add_text_material(user_id, course_id, payload)
    return CourseMaterialResponse(success=True, message="Text material uploaded", data=data)


@router.post(
    "/{course_id}/materials/file",
    response_model=CourseMaterialResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_file_material(
    course_id: str,
    file: UploadFile = File(..., description="Study material or problem set (PDF, PNG, JPG, TXT, MD, DOCX, PPTX …)"),
    mode: str = Query(default="study", description="Current workflow mode. Use 'study' for study uploads."),
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
) -> CourseMaterialResponse:
    """Upload a file for the selected mode.

    Accepted formats: PDF, PNG, JPG/JPEG, GIF, WEBP, TXT, MD, DOC, DOCX, PPTX.
    Maximum size: 50 MB.
    """
    import os
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
    if mode.lower() != "study":
        raise CourseServiceError(
            400,
            "UNSUPPORTED_MODE",
            "Only 'study' mode upload behavior is enabled right now.",
        )

    # Study mode requirement: store file bytes in course_materials.material
    # and extracted/metadata text in course_materials.text_material.
    data = course_service.add_study_file_material(user_id, course_id, file_bytes, filename, mime_type)
    return CourseMaterialResponse(success=True, message=f"'{filename}' uploaded successfully", data=data)


@router.get("/{course_id}/materials", response_model=CourseMaterialsResponse)
def list_materials(
    course_id: str,
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
) -> CourseMaterialsResponse:
    """Retrieve all materials for a course (with Supabase Storage URLs)."""
    data = course_service.list_materials(user_id, course_id)
    return CourseMaterialsResponse(success=True, message="Materials retrieved", data=data)


@router.get("/{course_id}/materials/{material_id}/download")
def download_material(
    course_id: str,
    material_id: str,
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
) -> RedirectResponse:
    """Redirect to the Supabase Storage URL to download the material file."""
    # Verify ownership by fetching the material
    materials = course_service.list_materials(user_id, course_id)
    material = next((m for m in materials if m.id == material_id), None)
    if not material:
        raise CourseServiceError(404, "MATERIAL_NOT_FOUND", "Material not found")
    if not material.storage_url:
        raise CourseServiceError(400, "NO_FILE", "This material has no downloadable file")

    return RedirectResponse(url=material.storage_url)
