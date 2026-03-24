import os
import uuid

from supabase import Client

from app.exceptions import CourseServiceError
from app.models import Course, CourseMaterial, CourseMaterialCreate, CourseCreate
from app.services.supabase_client import get_service_client

# Allowed upload extensions -> MIME types
ALLOWED_MIME_TYPES: set[str] = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "text/plain",
    "text/markdown",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
    "application/msword",  # .doc
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
}

ALLOWED_EXTENSIONS: set[str] = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".txt", ".md", ".doc", ".docx", ".pptx",
}

STORAGE_BUCKET = "materials"  # Supabase Storage bucket name
MAX_TEXT_PREVIEW = 5000  # Store first 5000 chars of txt/md in DB


class CourseService:
    def __init__(self, client: Client | None = None):
        self.client = client or get_service_client()

    # ── courses table ─────────────────────────────────────────────────────────

    def create_course(self, user_id: str, payload: CourseCreate) -> Course:
        record = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": payload.name,
            "details": payload.details,
        }
        try:
            response = self.client.table("courses").insert(record).execute()
        except Exception as exc:
            raise CourseServiceError(500, "COURSE_CREATE_FAILED", f"Failed to create course: {exc}") from exc

        data = response.data or []
        if not data:
            raise CourseServiceError(500, "COURSE_CREATE_FAILED", "Course creation returned no data")
        return self._serialize_course(data[0])

    def list_courses(self, user_id: str) -> list[Course]:
        response = (
            self.client.table("courses")
            .select("id, user_id, name, details, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return [self._serialize_course(row) for row in (response.data or [])]

    def get_course(self, user_id: str, course_id: str) -> Course:
        response = (
            self.client.table("courses")
            .select("id, user_id, name, details, created_at")
            .eq("id", course_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        data = response.data or []
        if not data:
            raise CourseServiceError(404, "COURSE_NOT_FOUND", "Course not found")
        return self._serialize_course(data[0])

    # ── course_materials table ────────────────────────────────────────────────

    def add_text_material(self, user_id: str, course_id: str, payload: CourseMaterialCreate) -> CourseMaterial:
        self._assert_course_owner(user_id, course_id)
        record = {
            "id": str(uuid.uuid4()),
            "course_id": course_id,
            "user_id": user_id,
            "is_text": True,
            "filename": "text_entry",
            "mime_type": "text/plain",
            "text_material": payload.text_material,
            "storage_url": None,  # No file uploaded for manual text entry
        }
        try:
            response = self.client.table("course_materials").insert(record).execute()
        except Exception as exc:
            raise CourseServiceError(500, "MATERIAL_CREATE_FAILED", f"Failed to save material: {exc}") from exc

        data = response.data or []
        if not data:
            raise CourseServiceError(500, "MATERIAL_CREATE_FAILED", "Material creation returned no data")
        return self._serialize_material(data[0])

    def add_file_material(
        self,
        user_id: str,
        course_id: str,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> CourseMaterial:
        self._assert_course_owner(user_id, course_id)

        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS and mime_type not in ALLOWED_MIME_TYPES:
            raise CourseServiceError(
                415,
                "UNSUPPORTED_FILE_TYPE",
                f"File type '{ext or mime_type}' is not allowed. "
                f"Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            )

        # Upload to Supabase Storage
        material_id = str(uuid.uuid4())
        storage_path = f"{course_id}/{material_id}{ext}"

        try:
            self.client.storage.from_(STORAGE_BUCKET).upload(storage_path, file_bytes)
        except Exception as exc:
            raise CourseServiceError(
                500,
                "STORAGE_UPLOAD_FAILED",
                f"Failed to upload file to storage: {exc}",
            ) from exc

        # Generate public URL
        storage_url = self.client.storage.from_(STORAGE_BUCKET).get_public_url(storage_path)

        # For text files, also store decoded content in DB for quick preview/search
        text_preview = None
        is_text_type = mime_type in {"text/plain", "text/markdown"} or ext in {".txt", ".md"}
        if is_text_type:
            try:
                text_preview = file_bytes.decode("utf-8")[:MAX_TEXT_PREVIEW]
            except UnicodeDecodeError:
                text_preview = file_bytes.decode("latin-1")[:MAX_TEXT_PREVIEW]

        # Store metadata in DB
        record = {
            "id": material_id,
            "course_id": course_id,
            "user_id": user_id,
            "is_text": is_text_type,
            "filename": filename,
            "mime_type": mime_type,
            "storage_url": storage_url,
            "text_material": text_preview,  # Only first 5000 chars if text
        }

        try:
            response = self.client.table("course_materials").insert(record).execute()
        except Exception as exc:
            # Try to clean up the uploaded file if DB insert fails
            try:
                self.client.storage.from_(STORAGE_BUCKET).remove([storage_path])
            except Exception:
                pass  # Cleanup error; don't mask the original error
            raise CourseServiceError(500, "MATERIAL_CREATE_FAILED", f"Failed to save material: {exc}") from exc

        data = response.data or []
        if not data:
            raise CourseServiceError(500, "MATERIAL_CREATE_FAILED", "File upload returned no data")
        return self._serialize_material(data[0])

    def add_study_file_material(
        self,
        user_id: str,
        course_id: str,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> CourseMaterial:
        """Store study uploads directly in course_materials.material/text_material."""
        self._assert_course_owner(user_id, course_id)

        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS and mime_type not in ALLOWED_MIME_TYPES:
            raise CourseServiceError(
                415,
                "UNSUPPORTED_FILE_TYPE",
                f"File type '{ext or mime_type}' is not allowed. "
                f"Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
            )

        encoded_material = "\\x" + file_bytes.hex()
        text_material = self._build_study_text_material(file_bytes, filename, mime_type, ext)
        is_text_type = mime_type in {"text/plain", "text/markdown"} or ext in {".txt", ".md"}

        record = {
            "id": str(uuid.uuid4()),
            "course_id": course_id,
            "user_id": user_id,
            "material": encoded_material,
            "text_material": text_material,
            "is_text": is_text_type,
        }

        try:
            response = self.client.table("course_materials").insert(record).execute()
        except Exception as exc:
            raise CourseServiceError(500, "MATERIAL_CREATE_FAILED", f"Failed to save study file: {exc}") from exc

        data = response.data or []
        if not data:
            raise CourseServiceError(500, "MATERIAL_CREATE_FAILED", "Study file upload returned no data")
        return self._serialize_material(data[0])

    def list_materials(self, user_id: str, course_id: str) -> list[CourseMaterial]:
        self._assert_course_owner(user_id, course_id)
        response = (
            self.client.table("course_materials")
            .select("id, course_id, user_id, is_text, text_material, created_at")
            .eq("course_id", course_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return [self._serialize_material(row) for row in (response.data or [])]

    # ── helpers ───────────────────────────────────────────────────────────────

    def _assert_course_owner(self, user_id: str, course_id: str) -> None:
        response = (
            self.client.table("courses")
            .select("id")
            .eq("id", course_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if not (response.data or []):
            raise CourseServiceError(404, "COURSE_NOT_FOUND", "Course not found")

    @staticmethod
    def _serialize_course(row: dict) -> Course:
        return Course(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            name=row["name"],
            details=row.get("details"),
            created_at=row.get("created_at"),
        )

    @staticmethod
    def _serialize_material(row: dict) -> CourseMaterial:
        return CourseMaterial(
            id=str(row["id"]),
            course_id=str(row["course_id"]),
            user_id=str(row["user_id"]),
            is_text=row["is_text"],
            filename=row.get("filename"),
            mime_type=row.get("mime_type"),
            storage_url=row.get("storage_url"),
            text_material=row.get("text_material"),  # Preview/full content for txt
            created_at=row.get("created_at"),
        )

    @staticmethod
    def _build_study_text_material(file_bytes: bytes, filename: str, mime_type: str, ext: str) -> str:
        """Return extracted text for text formats, otherwise store lightweight metadata."""
        is_text_type = mime_type in {"text/plain", "text/markdown"} or ext in {".txt", ".md"}
        if is_text_type:
            try:
                return file_bytes.decode("utf-8")[:MAX_TEXT_PREVIEW]
            except UnicodeDecodeError:
                return file_bytes.decode("latin-1")[:MAX_TEXT_PREVIEW]
        return f"filename={filename};mime={mime_type};note=binary_content_in_material"
