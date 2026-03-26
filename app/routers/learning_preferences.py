from fastapi import APIRouter, Depends, status

from app.dependencies import get_course_service, get_current_user_id
from app.models import (
    LearningPreferenceCreateRequest,
    LearningPreferenceItem,
    LearningPreferencesData,
    LearningPreferencesResponse,
)
from app.services.course_service import CourseService

router = APIRouter(prefix="/learning-preferences", tags=["learning-preferences"])


@router.get("", response_model=LearningPreferencesResponse)
def list_learning_preferences(
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
) -> LearningPreferencesResponse:
    detailed_items = course_service.get_user_learning_preferences_detailed(user_id)
    data = LearningPreferencesData(
        preferences=[LearningPreferenceItem.model_validate(item) for item in detailed_items]
    )
    return LearningPreferencesResponse(success=True, message="Learning preferences retrieved", data=data)


@router.post("", response_model=LearningPreferencesResponse, status_code=status.HTTP_201_CREATED)
def create_learning_preference(
    payload: LearningPreferenceCreateRequest,
    user_id: str = Depends(get_current_user_id),
    course_service: CourseService = Depends(get_course_service),
) -> LearningPreferencesResponse:
    course_service.add_user_learning_preference(user_id=user_id, preference=payload.preference)
    detailed_items = course_service.get_user_learning_preferences_detailed(user_id)
    data = LearningPreferencesData(
        preferences=[LearningPreferenceItem.model_validate(item) for item in detailed_items]
    )
    return LearningPreferencesResponse(success=True, message="Learning preference added", data=data)
