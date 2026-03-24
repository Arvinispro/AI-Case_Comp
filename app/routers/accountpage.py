from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

BASE_DIR = Path(__file__).resolve().parents[2]

router = APIRouter(tags=["account"])


@router.get("/account", include_in_schema=False)
def account_page() -> FileResponse:
	return FileResponse(BASE_DIR / "frontend" / "account" / "accountpage.html")


@router.get("/study-upload", include_in_schema=False)
def study_upload_page() -> HTMLResponse:
	return HTMLResponse(
		"<h1>Study Upload Page Coming Soon</h1><p>The study-upload page is not created yet.</p>",
		status_code=200,
	)


@router.get("/practice-upload", include_in_schema=False)
def practice_upload_page() -> HTMLResponse:
	return HTMLResponse(
		"<h1>Practice Upload Page Coming Soon</h1><p>The practice-upload page is not created yet.</p>",
		status_code=200,
	)
