from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.exceptions import AuthServiceError
from app.services.auth_service import AuthService

security_scheme = HTTPBearer(auto_error=False)


def get_auth_service() -> AuthService:
    return AuthService()


def get_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthServiceError(401, "MISSING_TOKEN", "Missing or invalid Authorization header")
    return credentials.credentials
