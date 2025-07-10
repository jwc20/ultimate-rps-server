from sqlmodel import SQLModel, Field
from typing import Optional
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm


class PlayerDB(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str

class RoomDB(SQLModel, table=True):
    id: str = Field(primary_key=True)
    name: str
    max_players: int
    number_of_actions: int
    game_over: bool
    round_number: int
    winner: Optional[str]
    started_at: Optional[str]
    # ended_at: Optional[str]
