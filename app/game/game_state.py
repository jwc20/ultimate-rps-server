
from typing import Dict, List, Optional, Set

import time
from fastapi import WebSocket
from dataclasses import dataclass, field
from rps import Game, FixedActionPlayer

import logging

log = logging.getLogger(__name__)


@dataclass
class PlayerInfo:
    user_id: str
    username: str
    connected_at: float
    actions_submitted: int = 0
    is_eliminated: bool = False


@dataclass
class GameRoundState:
    round_number: int
    actions: Dict[str, int] = field(default_factory=dict)
    ready_players: Set[str] = field(default_factory=set)

    def reset(self):
        self.actions.clear()
        self.ready_players.clear()
        self.round_number += 1


class GameState:

    def __init__(self, room_id: int, max_players: int, number_of_actions: int):
        log.info(f"Creating new room state for room {room_id}")
        self.room_id = room_id
        self.max_players = max_players
        self.number_of_actions = number_of_actions

        self._connections: Dict[str, WebSocket] = {}
        self._player_info: Dict[str, PlayerInfo] = {}

        self.game_active = False
        self.game_over = False
        self.winner: Optional[str] = None
        self.current_round = GameRoundState(round_number=1)
        self.eliminated_players: Set[str] = set()

    def __len__(self) -> int:
        return len(self._connections)

    @property
    def is_full(self) -> bool:
        return len(self._connections) >= self.max_players

    @property
    def active_players(self) -> List[str]:
        return [
            username
            for username, info in self._player_info.items()
            if not info.is_eliminated
        ]

    def add_player(self, user_id: str, username: str, websocket: WebSocket) -> None:
        if self.is_full:
            raise ValueError(f"Room {self.room_id} is full")
        if username in self._connections:
            raise ValueError(f"Player {username} already in room")

        log.info(f"Adding player {username} to room {self.room_id}")
        self._connections[username] = websocket
        self._player_info[username] = PlayerInfo(
            user_id=user_id, username=username, connected_at=time.time()
        )

    def remove_player(self, username: str) -> None:
        if username not in self._connections:
            return

        log.info(f"Removing player {username} from room {self.room_id}")
        del self._connections[username]
        del self._player_info[username]

        self.current_round.actions.pop(username, None)
        self.current_round.ready_players.discard(username)

    def submit_action(self, username: str, action: int) -> bool:
        if username not in self._player_info:
            return False
        if self._player_info[username].is_eliminated:
            return False
        if self.game_over:
            return False
        if action < 0 or action >= self.number_of_actions:
            return False

        self.current_round.actions[username] = action
        self.current_round.ready_players.add(username)
        self._player_info[username].actions_submitted += 1
        return True

    def all_players_ready(self) -> bool:
        return len(self.current_round.ready_players) == len(self.active_players)

    def process_round(self) -> Dict:
        if not self.all_players_ready():
            raise ValueError("Not all players ready")

        players = []
        actions = []
        for username, action in self.current_round.actions.items():
            players.append(FixedActionPlayer(username, action))
            actions.append(action)

        game = Game(players, self.number_of_actions)
        eliminated_indices = game.eliminate(actions)

        eliminated_usernames = []
        for idx in eliminated_indices:
            username = players[idx].name
            eliminated_usernames.append(username)
            self.eliminated_players.add(username)
            self._player_info[username].is_eliminated = True

        remaining = self.active_players

        if len(remaining) <= 1:
            self.game_over = True
            self.game_active = False
            self.winner = remaining[0] if remaining else None
        else:
            self.current_round.reset()

        return {
            "round": self.current_round.round_number - 1,
            "actions": dict(self.current_round.actions),
            "eliminated": eliminated_usernames,
            "remaining": remaining,
            "game_over": self.game_over,
            "winner": self.winner,
        }

    def start_game(self) -> bool:
        if len(self._connections) < 2:
            return False
        if self.game_active:
            return False

        self.reset_game()
        self.game_active = True
        return True

    def reset_game(self) -> None:
        self.game_active = False
        self.game_over = False
        self.winner = None
        self.current_round = GameRoundState(round_number=1)
        self.eliminated_players.clear()

        for info in self._player_info.values():
            info.is_eliminated = False