import mimetypes
import os
import uuid
from typing import Any
from urllib.parse import unquote, urlparse

from supabase import Client

from app.config import get_settings
from app.exceptions import AuthServiceError
from app.models import AuthData, LeaderboardUser, RewardXpData, SignInRequest, SignUpRequest, UserProfile
from app.services.supabase_client import get_default_client, get_service_client, get_user_client

PROFILE_PIC_BUCKET = "profile pic"
PROFILE_PIC_BUCKET_CANDIDATES = ["profile pic", "profile_pic", "profile-pic", "profilepic", "profile"]
PROFILE_PIC_ALLOWED_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
PROFILE_PIC_ALLOWED_MIME_TYPES: set[str] = {"image/png", "image/jpeg", "image/gif", "image/webp"}
PROFILE_PIC_MAX_BYTES = 5 * 1024 * 1024


class AuthService:
    def __init__(self, default_client: Client | None = None, service_client: Client | None = None):
        self.default_client = default_client or get_default_client()
        self.service_client = service_client or get_service_client()
        self._profile_bucket_name_cache: str | None = None

    def _get_profile_bucket_name(self) -> str:
        if self._profile_bucket_name_cache:
            return self._profile_bucket_name_cache

        candidates = PROFILE_PIC_BUCKET_CANDIDATES
        try:
            buckets = self.service_client.storage.list_buckets()
            bucket_ids: set[str] = set()
            for bucket in buckets or []:
                if isinstance(bucket, dict):
                    bucket_id = bucket.get("id") or bucket.get("name")
                else:
                    bucket_id = getattr(bucket, "id", None) or getattr(bucket, "name", None)
                if bucket_id:
                    bucket_ids.add(str(bucket_id))

            for candidate in candidates:
                if candidate in bucket_ids:
                    self._profile_bucket_name_cache = candidate
                    return candidate
        except Exception:
            pass

        self._profile_bucket_name_cache = PROFILE_PIC_BUCKET
        return PROFILE_PIC_BUCKET

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
            .select("id, username, xp, level, points, profile_pic, learning_type, created_at")
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
        resolved_profile_pic = self._resolve_profile_pic_url(profile_obj.get("profile_pic"))
        return UserProfile(
            id=str(profile_obj.get("id", user_id)),
            username=profile_obj.get("username"),
            xp=profile_obj.get("xp"),
            points=profile_obj.get("points"),
            level=profile_obj.get("level"),
            profile_pic=resolved_profile_pic,
            learning_type=str(profile_obj.get("learning_type")) if profile_obj.get("learning_type") else None,
            created_at=profile_obj.get("created_at"),
        )

    @staticmethod
    def _extract_bucket_and_storage_path(value: str) -> tuple[str | None, str | None]:
        if not value:
            return None, None

        if value.startswith("http://") or value.startswith("https://"):
            parsed = urlparse(value)
            path = unquote(parsed.path)

            public_marker = "/storage/v1/object/public/"
            sign_marker = "/storage/v1/object/sign/"

            if public_marker in path:
                remainder = path.split(public_marker, 1)[1]
                if "/" in remainder:
                    bucket, storage_path = remainder.split("/", 1)
                    return bucket, storage_path
            if sign_marker in path:
                remainder = path.split(sign_marker, 1)[1]
                if "/" in remainder:
                    bucket, storage_path = remainder.split("/", 1)
                    return bucket, storage_path
            return None, None

        return None, value

    def _resolve_profile_pic_url(self, value: str | None) -> str | None:
        if not value:
            return None

        # If DB already stores a valid signed URL, use it directly.
        if (
            (value.startswith("http://") or value.startswith("https://"))
            and "/storage/v1/object/sign/" in value
            and "token=" in value
        ):
            return value

        parsed_bucket, storage_path = self._extract_bucket_and_storage_path(value)
        if not storage_path:
            return value

        bucket_name = parsed_bucket or self._get_profile_bucket_name()

        try:
            signed = self.service_client.storage.from_(bucket_name).create_signed_url(storage_path, 3600)
            signed_url = None

            if isinstance(signed, dict):
                signed_url = (
                    signed.get("signedURL")
                    or signed.get("signedUrl")
                    or signed.get("signed_url")
                    or ((signed.get("data") or {}).get("signedURL") if isinstance(signed.get("data"), dict) else None)
                )
            elif isinstance(signed, str):
                signed_url = signed
            else:
                signed_url = (
                    getattr(signed, "signedURL", None)
                    or getattr(signed, "signedUrl", None)
                    or getattr(signed, "signed_url", None)
                )

            if signed_url:
                return self._normalize_storage_url(signed_url)
        except Exception:
            pass

        try:
            public_url = self.service_client.storage.from_(bucket_name).get_public_url(storage_path)
            return self._normalize_storage_url(public_url)
        except Exception:
            return value

    @staticmethod
    def _normalize_storage_url(url: str) -> str:
        if not url:
            return url

        if url.startswith("http://") or url.startswith("https://"):
            return url

        settings = get_settings()
        base = settings.supabase_url.rstrip("/")

        if url.startswith("/storage/v1/"):
            return f"{base}{url}"
        if url.startswith("/object/"):
            return f"{base}/storage/v1{url}"
        if url.startswith("object/"):
            return f"{base}/storage/v1/{url}"
        if url.startswith("/"):
            return f"{base}{url}"

        return f"{base}/{url}"

    @staticmethod
    def _calculate_level_from_xp(total_xp: int) -> int:
        return max(1, (max(0, total_xp) // 100) + 1)

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

    def get_leaderboard(self, limit: int = 10) -> list[LeaderboardUser]:
        safe_limit = max(1, min(limit, 50))
        response = (
            self.service_client.table("users")
            .select("username, level, points")
            .not_.is_("username", "null")
            .order("level", desc=True)
            .order("points", desc=True)
            .limit(safe_limit)
            .execute()
        )

        data = response.data or []
        leaderboard: list[LeaderboardUser] = []
        for row in data:
            username = row.get("username")
            if not username:
                continue
            level = row.get("level")
            leaderboard.append(LeaderboardUser(username=str(username), level=int(level or 0)))
        return leaderboard

    def award_xp(self, access_token: str, xp_amount: int) -> RewardXpData:
        if not access_token:
            raise AuthServiceError(401, "MISSING_TOKEN", "Missing bearer token")

        if xp_amount <= 0:
            raise AuthServiceError(400, "INVALID_XP", "XP must be greater than 0")

        try:
            user_client = get_user_client(access_token)
            user_response = user_client.auth.get_user(access_token)
        except Exception as exc:  # noqa: BLE001
            raise AuthServiceError(401, "INVALID_TOKEN", "Invalid or expired token") from exc

        user = getattr(user_response, "user", None)
        if user is None or not getattr(user, "id", None):
            raise AuthServiceError(401, "INVALID_TOKEN", "Invalid or expired token")

        user_id = str(user.id)
        profile = self._get_profile(user_id)
        if profile is None:
            raise AuthServiceError(404, "USER_NOT_FOUND", "User profile not found")

        current_xp = int(profile.get("xp") or 0)
        current_points = int(profile.get("points") or 0)

        total_xp = current_xp + int(xp_amount)
        total_points = current_points + int(xp_amount)
        level = self._calculate_level_from_xp(total_xp)

        try:
            self.service_client.table("users").update(
                {
                    "xp": total_xp,
                    "points": total_points,
                    "level": level,
                }
            ).eq("id", user_id).execute()
        except Exception as exc:  # noqa: BLE001
            raise AuthServiceError(500, "XP_REWARD_FAILED", f"Failed to apply XP reward: {exc}") from exc

        return RewardXpData(awarded_xp=int(xp_amount), total_xp=total_xp, points=total_points, level=level)

    def upload_profile_picture(
        self,
        access_token: str,
        file_bytes: bytes,
        filename: str,
        mime_type: str,
    ) -> UserProfile:
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

        if len(file_bytes) > PROFILE_PIC_MAX_BYTES:
            raise AuthServiceError(413, "FILE_TOO_LARGE", "Profile picture must be 5 MB or smaller")

        ext = os.path.splitext(filename)[1].lower()
        if ext not in PROFILE_PIC_ALLOWED_EXTENSIONS and mime_type not in PROFILE_PIC_ALLOWED_MIME_TYPES:
            raise AuthServiceError(
                415,
                "UNSUPPORTED_FILE_TYPE",
                "Profile picture must be png, jpg, jpeg, gif, or webp",
            )

        user_id = str(user.id)
        picture_id = str(uuid.uuid4())
        safe_ext = ext if ext else ".png"
        storage_path = f"{user_id}/{picture_id}{safe_ext}"
        bucket_name = self._get_profile_bucket_name()

        normalized_mime = (mime_type or "").strip().lower()
        if normalized_mime not in PROFILE_PIC_ALLOWED_MIME_TYPES:
            guessed_mime = mimetypes.guess_type(filename)[0]
            normalized_mime = (guessed_mime or "application/octet-stream").lower()

        if normalized_mime not in PROFILE_PIC_ALLOWED_MIME_TYPES:
            raise AuthServiceError(
                415,
                "UNSUPPORTED_FILE_TYPE",
                "Profile picture must be png, jpg, jpeg, gif, or webp",
            )

        try:
            self.service_client.storage.from_(bucket_name).upload(
                storage_path,
                file_bytes,
                file_options={"content-type": normalized_mime},
            )
        except Exception as exc:  # noqa: BLE001
            raw_error = str(exc)
            if "Bucket not found" in raw_error:
                raise AuthServiceError(
                    500,
                    "STORAGE_BUCKET_NOT_FOUND",
                    "Profile picture bucket not found. Please create one named profile_pic, profile-pic, or profile pic.",
                ) from exc
            raise AuthServiceError(500, "STORAGE_UPLOAD_FAILED", f"Failed to upload profile picture: {exc}") from exc

        signed = self.service_client.storage.from_(bucket_name).create_signed_url(storage_path, 60 * 60 * 24 * 365)
        signed_url = None
        if isinstance(signed, dict):
            signed_url = (
                signed.get("signedURL")
                or signed.get("signedUrl")
                or signed.get("signed_url")
                or ((signed.get("data") or {}).get("signedURL") if isinstance(signed.get("data"), dict) else None)
            )
        elif isinstance(signed, str):
            signed_url = signed
        else:
            signed_url = (
                getattr(signed, "signedURL", None)
                or getattr(signed, "signedUrl", None)
                or getattr(signed, "signed_url", None)
            )

        if signed_url:
            profile_pic_url = self._normalize_storage_url(signed_url)
        else:
            public_url = self.service_client.storage.from_(bucket_name).get_public_url(storage_path)
            profile_pic_url = self._normalize_storage_url(public_url)

        try:
            self.service_client.table("users").update({"profile_pic": profile_pic_url}).eq("id", user_id).execute()
        except Exception as exc:  # noqa: BLE001
            raise AuthServiceError(500, "PROFILE_UPDATE_FAILED", f"Failed to save profile picture URL: {exc}") from exc

        profile = self._get_profile(user_id)
        return self._serialize_profile(user, profile)
