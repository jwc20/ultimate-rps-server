from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class Room:
    room_name: str
    created_by: int
    max_players: int | None = None
    number_of_players: int = 0
    number_of_actions: int | None = None
    created_at: str = None
    disabled: bool = False
    id: int | None = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc).isoformat()