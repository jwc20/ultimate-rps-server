from sqlmodel import Field, SQLModel
from datetime import datetime, timezone

class RoomBase(SQLModel):
    room_name: str = Field(index=True)
    max_players: int = Field(default=None)
    number_of_actions: int = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    disabled: bool = Field(default=False)
    

class Room(RoomBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_by: int = Field(foreign_key="user.id", index=True)
    
    
    
# class RoomUserInfo(BaseModel):
#     """Chatroom user metadata."""
#     user_id: int
#     connected_at: float
#     message_count: int