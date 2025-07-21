from models.room import RoomBase


class RoomCreate(RoomBase):
    room_name: str
    max_players: int | None = 2
    number_of_actions: int | None = 3