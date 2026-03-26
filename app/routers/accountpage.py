from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

BASE_DIR = Path(__file__).resolve().parents[2]

router = APIRouter(tags=["account"])


@router.get("/account", include_in_schema=False)
def account_page() -> FileResponse:
    return FileResponse(BASE_DIR / "frontend" / "account" / "accountpage.html")


@router.get("/profile", include_in_schema=False)
def profile_page() -> FileResponse:
    return FileResponse(BASE_DIR / "frontend" / "account" / "profile.html")


@router.get("/learning-preferences", include_in_schema=False)
def learning_preferences_page() -> FileResponse:
    return FileResponse(BASE_DIR / "frontend" / "account" / "learning_preferences.html")
