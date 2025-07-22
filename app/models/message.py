from datetime import datetime, timezone
from sqlmodel import Field, SQLModel


class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    room_id: int = Field(foreign_key="room.id", index=True)
    username: str
    message: str
    type: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))