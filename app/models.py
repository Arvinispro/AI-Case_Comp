from typing import Literal

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
    profile_pic: str | None = None
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


class LeaderboardUser(BaseModel):
    username: str
    level: int


class LeaderboardResponse(BaseModel):
    success: bool = True
    message: str
    data: list[LeaderboardUser] = []
    error: ErrorDetail | None = None


class RewardXpRequest(BaseModel):
    xp: int = Field(ge=1, le=720)


class RewardXpData(BaseModel):
    awarded_xp: int
    total_xp: int
    points: int
    level: int


class RewardXpResponse(BaseModel):
    success: bool = True
    message: str
    data: RewardXpData | None = None
    error: ErrorDetail | None = None


class MessageData(BaseModel):
    action: str
    problem_id: str | None = None


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


class PresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=500)
    mime_type: str = Field(min_length=1, max_length=200)

    model_config = ConfigDict(str_strip_whitespace=True)


class PresignResponse(BaseModel):
    success: bool = True
    storage_path: str
    signed_url: str


class ConfirmUploadRequest(BaseModel):
    storage_path: str = Field(min_length=1, max_length=1000)
    filename: str = Field(min_length=1, max_length=500)
    mime_type: str = Field(min_length=1, max_length=200)

    model_config = ConfigDict(str_strip_whitespace=True)


class PracticeChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    material_files: list[str] = Field(default_factory=list, max_length=20)
    problem_id: str | None = Field(default=None, max_length=100)
    course_id: str | None = Field(default=None, max_length=100)

    model_config = ConfigDict(str_strip_whitespace=True)


class PracticeChatData(BaseModel):
    reply: str


class PracticeChatResponse(BaseModel):
    success: bool = True
    message: str
    data: PracticeChatData | None = None
    error: ErrorDetail | None = None


class StudyChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    material_files: list[str] = Field(default_factory=list, max_length=50)
    course_id: str | None = Field(default=None, max_length=100)

    model_config = ConfigDict(str_strip_whitespace=True)


class StudyChatData(BaseModel):
    reply: str


class StudyChatResponse(BaseModel):
    success: bool = True
    message: str
    data: StudyChatData | None = None
    error: ErrorDetail | None = None


class StudyScheduleRequest(BaseModel):
    duration_minutes: int = Field(ge=1, le=720)
    material_files: list[str] = Field(default_factory=list, max_length=50)
    course_id: str | None = Field(default=None, max_length=100)

    model_config = ConfigDict(str_strip_whitespace=True)


class StudyScheduleItem(BaseModel):
    duration_minutes: int = Field(ge=1)
    activity_type: Literal["work", "break", "quiz"]
    activity: str = Field(min_length=1)


class StudyScheduleData(BaseModel):
    schedule_items: list[StudyScheduleItem] = Field(default_factory=list)
    learning_preferences: list[str] = Field(default_factory=list)
    duration_minutes: int
    material_files: list[str] = Field(default_factory=list)
    generated_at: str
    course_id: str | None = None


class StudyScheduleResponse(BaseModel):
    success: bool = True
    message: str
    data: StudyScheduleData | None = None
    error: ErrorDetail | None = None


class LearningPreferenceItem(BaseModel):
    id: str
    preference: str
    created_at: str | None = None
    source: Literal["table", "profile_learning_type"] = "table"


class LearningPreferencesData(BaseModel):
    preferences: list[LearningPreferenceItem] = Field(default_factory=list)


class LearningPreferencesResponse(BaseModel):
    success: bool = True
    message: str
    data: LearningPreferencesData = Field(default_factory=LearningPreferencesData)
    error: ErrorDetail | None = None


class LearningPreferenceCreateRequest(BaseModel):
    preference: str = Field(min_length=1, max_length=200)

    model_config = ConfigDict(str_strip_whitespace=True)
