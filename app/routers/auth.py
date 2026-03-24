from fastapi import APIRouter, Depends, status

from app.dependencies import get_auth_service, get_bearer_token
from app.models import AuthResponse, MessageData, MessageResponse, SignInRequest, SignUpRequest, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/sign_up", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def sign_up(payload: SignUpRequest, auth_service: AuthService = Depends(get_auth_service)) -> AuthResponse:
    data = auth_service.sign_up(payload)
    return AuthResponse(success=True, message="User signed up successfully", data=data)


@router.post("/sign_in", response_model=AuthResponse)
def sign_in(payload: SignInRequest, auth_service: AuthService = Depends(get_auth_service)) -> AuthResponse:
    data = auth_service.sign_in(payload)
    return AuthResponse(success=True, message="User signed in successfully", data=data)


@router.post("/log_out", response_model=MessageResponse)
def log_out(
    token: str = Depends(get_bearer_token),
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    auth_service.log_out(token)
    return MessageResponse(success=True, message="User logged out successfully", data=MessageData(action="logged_out"))


@router.get("/current_user", response_model=UserResponse)
def get_current_user(
    token: str = Depends(get_bearer_token),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    data = auth_service.get_current_user(token)
    return UserResponse(success=True, message="Current user retrieved", data=data)
