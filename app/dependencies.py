from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.exceptions import AuthServiceError
from app.services.auth_service import AuthService
from app.services.llm_service import LLMService
from app.services.session_material_store import SessionMaterialStore
from app.services.session_schedule_store import SessionScheduleStore
from app.services.supabase_client import get_default_client

security_scheme = HTTPBearer(auto_error=False)
_session_material_store = SessionMaterialStore()
_session_schedule_store = SessionScheduleStore()


def get_auth_service() -> AuthService:
    return AuthService()


def get_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthServiceError(401, "MISSING_TOKEN", "Missing or invalid Authorization header")
    return credentials.credentials


def get_current_user_id(token: str = Depends(get_bearer_token)) -> str:
    """Verify the JWT with Supabase and return the user id."""
    try:
        client = get_default_client()
        response = client.auth.get_user(token)
        user = getattr(response, "user", None)
        if user is None or not getattr(user, "id", None):
            raise AuthServiceError(401, "INVALID_TOKEN", "Invalid or expired token")
        return str(user.id)
    except AuthServiceError:
        raise
    except Exception as exc:
        raise AuthServiceError(401, "INVALID_TOKEN", "Could not verify token") from exc


def get_course_service():
    from app.services.course_service import CourseService
    return CourseService()


def get_session_material_store() -> SessionMaterialStore:
    return _session_material_store


def get_session_schedule_store() -> SessionScheduleStore:
    return _session_schedule_store


def get_llm_service() -> LLMService:
    return LLMService()


def get_chat_orchestrator_service(
    course_service=Depends(get_course_service),
    llm_service=Depends(get_llm_service),
    session_material_store: SessionMaterialStore = Depends(get_session_material_store),
    session_schedule_store: SessionScheduleStore = Depends(get_session_schedule_store),
):
    from app.services.chat_orchestrator_service import ChatOrchestratorService

    return ChatOrchestratorService(
        course_service=course_service,
        llm_service=llm_service,
        session_material_store=session_material_store,
        session_schedule_store=session_schedule_store,
    )
