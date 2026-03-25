from collections import defaultdict
from threading import Lock

from app.models import CourseMaterial

_MAX_STORED_PER_USER = 200


class SessionMaterialStore:
    """In-memory material store scoped to a logged-in user's active app session."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._materials_by_user: dict[str, list[CourseMaterial]] = defaultdict(list)

    def add_material(self, user_id: str, material: CourseMaterial) -> None:
        with self._lock:
            current = self._materials_by_user[user_id]
            current = [item for item in current if item.id != material.id]
            current.insert(0, material)
            self._materials_by_user[user_id] = current[:_MAX_STORED_PER_USER]

    def list_materials(self, user_id: str) -> list[CourseMaterial]:
        with self._lock:
            return list(self._materials_by_user.get(user_id, []))

    def clear_materials(self, user_id: str) -> None:
        with self._lock:
            self._materials_by_user.pop(user_id, None)
