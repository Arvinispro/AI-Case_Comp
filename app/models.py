from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict | list | None = None


class UserProfile(BaseModel):
    id: str
    username: str | None = None
    xp: int | None = None
    level: int | None = None
    points: int | None = None
    learning_type: str | None = None
    created_at: str | None = None


class AuthData(BaseModel):
    user: UserProfile
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"


class AuthResponse(BaseModel):
    success: bool = True
    message: str
    data: AuthData | None = None
    error: ErrorDetail | None = None


class UserResponse(BaseModel):
    success: bool = True
    message: str
    data: UserProfile | None = None
    error: ErrorDetail | None = None


class MessageData(BaseModel):
    action: str


class MessageResponse(BaseModel):
    success: bool = True
    message: str
    data: MessageData | None = None
    error: ErrorDetail | None = None


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    username: str = Field(min_length=3, max_length=50)

    model_config = ConfigDict(str_strip_whitespace=True)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        has_upper = any(char.isupper() for char in value)
        has_lower = any(char.islower() for char in value)
        has_digit = any(char.isdigit() for char in value)
        if not (has_upper and has_lower and has_digit):
            raise ValueError("password must include uppercase, lowercase, and a number")
        return value

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not value.replace("_", "").replace("-", "").isalnum():
            raise ValueError("username can contain letters, numbers, '_' and '-'")
        return value


class SignInRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    model_config = ConfigDict(str_strip_whitespace=True)


# ── Courses ───────────────────────────────────────────────────────────────────

class Course(BaseModel):
    id: str
    user_id: str
    name: str
    details: str | None = None
    created_at: str | None = None


class CourseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    details: str | None = Field(default=None, max_length=2000)

    model_config = ConfigDict(str_strip_whitespace=True)


class CourseResponse(BaseModel):
    success: bool = True
    message: str
    data: Course | None = None
    error: ErrorDetail | None = None


class CoursesResponse(BaseModel):
    success: bool = True
    message: str
    data: list[Course] = []
    error: ErrorDetail | None = None


# ── Course materials ──────────────────────────────────────────────────────────

class CourseMaterial(BaseModel):
    id: str
    course_id: str
    user_id: str
    is_text: bool
    filename: str | None = None       # original upload name
    mime_type: str | None = None      # detected content type
    storage_url: str | None = None    # Supabase Storage public URL
    text_material: str | None = None  # only for .txt/.md of short length
    created_at: str | None = None


class CourseMaterialCreate(BaseModel):
    text_material: str = Field(min_length=1)

    model_config = ConfigDict(str_strip_whitespace=True)


class CourseMaterialResponse(BaseModel):
    success: bool = True
    message: str
    data: CourseMaterial | None = None
    error: ErrorDetail | None = None


class CourseMaterialsResponse(BaseModel):
    success: bool = True
    message: str
    data: list[CourseMaterial] = []
    error: ErrorDetail | None = None
