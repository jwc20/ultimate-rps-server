from pydantic import BaseModel


class PlayerInfo(BaseModel):
    user_id: str
    username: str
    connected_at: float
    actions_submitted: int = 0
    is_eliminated: bool = False


class GameRoundState(BaseModel):
    round_number: int
    actions: dict[str, int] = dict()
    ready_players: set[str] = set()

    def reset(self):
        self.actions.clear()
        self.ready_players.clear()
        self.round_number += 1
