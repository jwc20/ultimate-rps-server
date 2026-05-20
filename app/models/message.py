from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Message:
    room_id: int
    username: str
    message: str
    type: str
    created_at: str = None
    id: int | None = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc).isoformat()