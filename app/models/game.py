from collections import namedtuple
from typing import Dict, List, Optional
from fastapi import WebSocket

PlayerAction = namedtuple("PlayerAction", ["player_id", "message_id", "action"])
RoomPlayer = namedtuple("RoomPlayer", ["player", "locked"])

class Player:
    def __init__(self, player_id: str, name: str):
        self.id = player_id
        self.name = name
        self.current_room: Optional[str] = None
        self.websocket: Optional[WebSocket] = None


class Room:
    def __init__(
            self, room_id: str, name: str, max_players: int, number_of_actions: int
    ):
        self.id = room_id
        self.name = name
        self.number_of_actions = number_of_actions
        self.max_players = max_players
        self.players: Dict[str, RoomPlayer] = {}
        self.messages: List[dict] = []
        self.round_number = 0
        self.game_rounds: Dict[int, List[PlayerAction]] = {}
        self.game_round_results: Dict[int, List[str]] = {}