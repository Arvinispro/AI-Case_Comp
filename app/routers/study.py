import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse

from app.dependencies import get_course_service, get_current_user_id
from app.exceptions import CourseServiceError
from app.models import (
	ConfirmUploadRequest,
	CourseCreate,
	CourseMaterialCreate,
	CourseMaterialResponse,
	CourseMaterialsResponse,
	CourseResponse,
	CoursesResponse,
	PresignRequest,
	PresignResponse,
)
from app.services.course_service import ALLOWED_EXTENSIONS, CourseService

page_router = APIRouter(tags=["study-pages"])
router = APIRouter(prefix="/study", tags=["study"])

_MAX_FILE_BYTES = 50 * 1024 * 1024


@page_router.get("/study", include_in_schema=False)
def study_upload_page() -> FileResponse:
	return FileResponse(
		Path(__file__).parent.parent.parent / "frontend" / "studyupload" / "uploadstudy.html",
		media_type="text/html",
	)


@router.post("/courses", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
def create_study_course(
	payload: CourseCreate,
	user_id: str = Depends(get_current_user_id),
	course_service: CourseService = Depends(get_course_service),
) -> CourseResponse:
	data = course_service.create_course(user_id, payload)
	return CourseResponse(success=True, message="Study course created successfully", data=data)


@router.get("/courses", response_model=CoursesResponse)
def list_study_courses(
	user_id: str = Depends(get_current_user_id),
	course_service: CourseService = Depends(get_course_service),
) -> CoursesResponse:
	data = course_service.list_courses(user_id)
	return CoursesResponse(success=True, message="Study courses retrieved", data=data)


@router.get("/courses/{course_id}", response_model=CourseResponse)
def get_study_course(
	course_id: str,
	user_id: str = Depends(get_current_user_id),
	course_service: CourseService = Depends(get_course_service),
) -> CourseResponse:
	data = course_service.get_course(user_id, course_id)
	return CourseResponse(success=True, message="Study course retrieved", data=data)


@router.post(
	"/courses/{course_id}/materials/text",
	response_model=CourseMaterialResponse,
	status_code=status.HTTP_201_CREATED,
)
def upload_study_text_material(
	course_id: str,
	payload: CourseMaterialCreate,
	user_id: str = Depends(get_current_user_id),
	course_service: CourseService = Depends(get_course_service),
) -> CourseMaterialResponse:
	data = course_service.add_text_material(user_id, course_id, payload)
	return CourseMaterialResponse(success=True, message="Study text material uploaded", data=data)


@router.post(
	"/courses/{course_id}/materials/file",
	response_model=CourseMaterialResponse,
	status_code=status.HTTP_201_CREATED,
)
def upload_study_file_material(
	course_id: str,
	file: UploadFile = File(..., description="Study material upload"),
	user_id: str = Depends(get_current_user_id),
	course_service: CourseService = Depends(get_course_service),
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
	data = course_service.add_study_file_material(user_id, course_id, file_bytes, filename, mime_type)
	return CourseMaterialResponse(success=True, message=f"'{filename}' uploaded successfully", data=data)


@router.post(
	"/courses/{course_id}/materials/presign",
	response_model=PresignResponse,
)
def presign_study_file(
	course_id: str,
	payload: PresignRequest,
	user_id: str = Depends(get_current_user_id),
	course_service: CourseService = Depends(get_course_service),
) -> PresignResponse:
	"""Generate a signed upload URL so the browser can upload a file directly to storage."""
	result = course_service.presign_study_upload(user_id, course_id, payload.filename, payload.mime_type)
	return PresignResponse(storage_path=result["storage_path"], signed_url=result["signed_url"])


@router.post(
	"/courses/{course_id}/materials/confirm",
	response_model=CourseMaterialResponse,
	status_code=status.HTTP_201_CREATED,
)
def confirm_study_file(
	course_id: str,
	payload: ConfirmUploadRequest,
	user_id: str = Depends(get_current_user_id),
	course_service: CourseService = Depends(get_course_service),
) -> CourseMaterialResponse:
	"""Record a file that was already uploaded directly from the browser into the DB."""
	data = course_service.confirm_study_upload(
		user_id, course_id, payload.storage_path, payload.filename, payload.mime_type
	)
	return CourseMaterialResponse(success=True, message=f"'{payload.filename}' recorded successfully", data=data)


@router.get("/courses/{course_id}/materials", response_model=CourseMaterialsResponse)
def list_study_materials(
	course_id: str,
	user_id: str = Depends(get_current_user_id),
	course_service: CourseService = Depends(get_course_service),
) -> CourseMaterialsResponse:
	data = course_service.list_materials(user_id, course_id)
	return CourseMaterialsResponse(success=True, message="Study materials retrieved", data=data)
