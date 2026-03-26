from collections import defaultdict
from threading import Lock

_MAX_STORED_SCHEDULES_PER_USER = 5


class SessionScheduleStore:
    """In-memory study schedule store scoped to each logged-in user's active app session."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._schedules_by_user: dict[str, list[dict]] = defaultdict(list)

    def set_latest_schedule(self, user_id: str, payload: dict) -> None:
        with self._lock:
            current = self._schedules_by_user[user_id]
            current.insert(0, payload)
            self._schedules_by_user[user_id] = current[:_MAX_STORED_SCHEDULES_PER_USER]

    def get_latest_schedule(self, user_id: str) -> dict | None:
        with self._lock:
            current = self._schedules_by_user.get(user_id, [])
            return dict(current[0]) if current else None

    def clear_schedules(self, user_id: str) -> None:
        with self._lock:
            self._schedules_by_user.pop(user_id, None)
