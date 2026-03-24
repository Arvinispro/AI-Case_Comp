from typing import Any

from supabase import Client

from app.exceptions import AuthServiceError
from app.models import AuthData, SignInRequest, SignUpRequest, UserProfile
from app.services.supabase_client import get_default_client, get_service_client, get_user_client


class AuthService:
    def __init__(self, default_client: Client | None = None, service_client: Client | None = None):
        self.default_client = default_client or get_default_client()
        self.service_client = service_client or get_service_client()

    @staticmethod
    def _extract_user(auth_response: Any) -> Any | None:
        user = getattr(auth_response, "user", None)
        if user is not None:
            return user
        data = getattr(auth_response, "data", None)
        return getattr(data, "user", None)

    @staticmethod
    def _extract_session(auth_response: Any) -> Any | None:
        session = getattr(auth_response, "session", None)
        if session is not None:
            return session
        data = getattr(auth_response, "data", None)
        return getattr(data, "session", None)

    def _get_profile(self, user_id: str) -> dict | None:
        response = (
            self.service_client.table("users")
            .select("id, username, xp, level, learning_type, created_at")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        data = response.data or []
        return data[0] if data else None

    def _serialize_profile(self, user_obj: Any, profile_obj: dict | None) -> UserProfile:
        user_id = str(getattr(user_obj, "id", ""))
        if not user_id:
            raise AuthServiceError(500, "SUPABASE_RESPONSE_ERROR", "Missing user id from Supabase response")

        if profile_obj is None:
            return UserProfile(id=user_id)

        return UserProfile(
            id=str(profile_obj.get("id", user_id)),
            username=profile_obj.get("username"),
            xp=profile_obj.get("xp"),
            level=profile_obj.get("level"),
            learning_type=str(profile_obj.get("learning_type")) if profile_obj.get("learning_type") else None,
            created_at=profile_obj.get("created_at"),
        )

    @staticmethod
    def _build_auth_data(user: UserProfile, session_obj: Any | None) -> AuthData:
        if session_obj is None:
            return AuthData(user=user)

        access_token = getattr(session_obj, "access_token", None)
        refresh_token = getattr(session_obj, "refresh_token", None)
        return AuthData(
            user=user,
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )

    def sign_up(self, payload: SignUpRequest) -> AuthData:
        username_exists = (
            self.service_client.table("users").select("id").eq("username", payload.username).limit(1).execute()
        )
        if username_exists.data:
            raise AuthServiceError(409, "USERNAME_ALREADY_EXISTS", "Username already exists")

        try:
            auth_response = self.default_client.auth.sign_up(
                {
                    "email": payload.email,
                    "password": payload.password,
                    "options": {"data": {"username": payload.username}},
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise AuthServiceError(400, "SIGN_UP_FAILED", f"Unable to sign up: {str(exc)}") from exc

        user = self._extract_user(auth_response)
        session = self._extract_session(auth_response)

        if user is None or not getattr(user, "id", None):
            raise AuthServiceError(400, "SIGN_UP_FAILED", "Supabase did not return a valid user")

        user_id = str(user.id)

        try:
            self.service_client.table("users").insert(
                {
                    "id": user_id,
                    "username": payload.username,
                    "xp": 0,
                    "level": 1,
                    "learning_type": None,
                    "points": 0,
                }
            ).execute()
        except Exception as exc:  # noqa: BLE001
            try:
                self.service_client.auth.admin.delete_user(user_id)
            except Exception:  # noqa: BLE001
                pass
            raise AuthServiceError(
                500,
                "PROFILE_CREATE_FAILED",
                "Auth user created, but failed to create public.users profile",
                details={"reason": str(exc)},
            ) from exc

        profile = self._get_profile(user_id)
        serialized = self._serialize_profile(user, profile)
        return self._build_auth_data(serialized, session)

    def sign_in(self, payload: SignInRequest) -> AuthData:
        try:
            auth_response = self.default_client.auth.sign_in_with_password(
                {
                    "email": payload.email,
                    "password": payload.password,
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise AuthServiceError(401, "INVALID_CREDENTIALS", "Invalid email or password") from exc

        user = self._extract_user(auth_response)
        session = self._extract_session(auth_response)

        if user is None or session is None:
            raise AuthServiceError(401, "INVALID_CREDENTIALS", "Invalid email or password")

        profile = self._get_profile(str(user.id))
        serialized = self._serialize_profile(user, profile)
        return self._build_auth_data(serialized, session)

    def log_out(self, access_token: str) -> None:
        if not access_token:
            raise AuthServiceError(401, "MISSING_TOKEN", "Missing bearer token")

        try:
            user_client = get_user_client(access_token)
            user_response = user_client.auth.get_user(access_token)
            user = getattr(user_response, "user", None)
            if user is None or not getattr(user, "id", None):
                raise ValueError("Invalid or expired token")
            user_client.auth.sign_out()
        except Exception as exc:  # noqa: BLE001
            raise AuthServiceError(401, "LOG_OUT_FAILED", "Unable to log out with provided token") from exc

    def get_current_user(self, access_token: str) -> UserProfile:
        if not access_token:
            raise AuthServiceError(401, "MISSING_TOKEN", "Missing bearer token")

        try:
            user_client = get_user_client(access_token)
            user_response = user_client.auth.get_user(access_token)
        except Exception as exc:  # noqa: BLE001
            raise AuthServiceError(401, "INVALID_TOKEN", "Invalid or expired token") from exc

        user = getattr(user_response, "user", None)
        if user is None or not getattr(user, "id", None):
            raise AuthServiceError(401, "INVALID_TOKEN", "Invalid or expired token")

        profile = self._get_profile(str(user.id))
        return self._serialize_profile(user, profile)
