from sqlmodel import Field, SQLModel


class RoomBase(SQLModel):
    room_name: str = Field(index=True)
    max_players: int = Field(default=None)
    number_of_actions: int = Field(default=None)
    disabled: bool = Field(default=False)


class Room(RoomBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    
    
    
# class RoomUserInfo(BaseModel):
#     """Chatroom user metadata."""
#     user_id: int
#     connected_at: float
#     message_count: int