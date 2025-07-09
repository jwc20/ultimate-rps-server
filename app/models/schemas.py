from pydantic import BaseModel
from typing import List, Optional

class PlayerCreateRequest(BaseModel):
    player_name: str


class PlayerResponse(BaseModel):
    player_id: str
    player_name: str


class RoomCreateRequest(BaseModel):
    room_name: str
    max_players: str
    number_of_actions: str
    player_id: str


class RoomJoinRequest(BaseModel):
    room_id: str
    player_id: str


class RoomResponse(BaseModel):
    id: str
    name: str
    player_count: int
    max_players: int
    number_of_actions: int