from pydantic import BaseModel


class RoomCreate(BaseModel):
    room_name: str
    max_players: int | None = 2
    number_of_actions: int | None = 3