import json
import time
from typing import Dict, Set, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import logging

from fastapi import WebSocket, Depends, Query, HTTPException, status
from sqlmodel import Session, select
import jwt
import anyio
from broadcaster import Broadcast

from ..models import Room, Message, User
from rps import Game, FixedActionPlayer
from ..database import get_session
from .auth import get_user_by_username

log = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, Query, WebSocket, status
from ..config import SECRET_KEY, ALGORITHM

router = APIRouter()


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


class RoomState:

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


class RoomManager:

    def __init__(self, broadcast: Broadcast):
        self.broadcast = broadcast
        self.rooms: Dict[str, RoomState] = {}

    async def get_or_create_room(self, room_id: str, session: Session) -> RoomState:
        if room_id not in self.rooms:
            room = session.exec(select(Room).where(Room.id == int(room_id))).first()
            if not room:
                raise ValueError(f"Room {room_id} not found in database")

            self.rooms[room_id] = RoomState(
                room_id=int(room_id),
                max_players=room.max_players,
                number_of_actions=room.number_of_actions,
            )

        return self.rooms[room_id]

    async def broadcast_to_room(self, room_id: str, message: Dict) -> None:
        await self.broadcast.publish(
            channel=f"chatroom_{room_id}", message=json.dumps(message)
        )

    async def handle_player_action(
        self, room_id: str, username: str, action: int
    ) -> None:
        room = self.rooms.get(room_id)
        if not room:
            return

        if room.submit_action(username, action):
            await self.broadcast_to_room(
                room_id,
                {
                    "type": "player_ready",
                    "username": username,
                    "ready_count": len(room.current_round.ready_players),
                    "total_active": len(room.active_players),
                },
            )

            if room.all_players_ready():
                try:
                    results = room.process_round()
                    await self.broadcast_to_room(
                        room_id, {"type": "round_complete", **results}
                    )
                except Exception as e:
                    log.error(f"Error processing round: {e}")
                    await self.broadcast_to_room(
                        room_id, {"type": "error", "message": "Failed to process round"}
                    )


room_manager: Optional[RoomManager] = None


def get_room_manager() -> RoomManager:
    if room_manager is None:
        raise RuntimeError("Room manager not initialized")
    return room_manager


async def websocket_receiver(
    websocket: WebSocket,
    room_id: str,
    user_id: str,
    username: str,
    session: Session,
    manager: RoomManager,
) -> None:
    room = await manager.get_or_create_room(room_id, session)

    try:
        room.add_player(user_id, username, websocket)
        await manager.broadcast_to_room(
            room_id,
            {
                "type": "player_joined",
                "username": username,
                "players": room.active_players,
            },
        )

        async for message in websocket.iter_text():
            try:
                msg_data = json.loads(message)
                msg_type = msg_data.get("type")

                if msg_type == "play":
                    action = int(msg_data.get("message", 0))
                    await manager.handle_player_action(room_id, username, action)

                elif msg_type == "start_game":
                    if room.start_game():
                        await manager.broadcast_to_room(
                            room_id,
                            {"type": "game_started", "players": room.active_players},
                        )

                elif msg_type == "reset_game" and room.game_over:
                    room.reset_game()
                    await manager.broadcast_to_room(
                        room_id, {"type": "game_reset", "players": room.active_players}
                    )

                elif msg_type == "message":
                    db_message = Message(
                        room_id=int(room_id),
                        username=username,
                        message=msg_data.get("message", ""),
                        type="message",
                    )
                    session.add(db_message)
                    session.commit()

                    await manager.broadcast_to_room(
                        room_id,
                        {
                            "type": "message",
                            "username": username,
                            "message": msg_data.get("message", ""),
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                    )

            except (json.JSONDecodeError, ValueError) as e:
                log.error(f"Error processing message from {username}: {e}")
                await websocket.send_json(
                    {"type": "error", "message": "Invalid message format"}
                )

    finally:
        room.remove_player(username)
        await manager.broadcast_to_room(
            room_id,
            {
                "type": "player_left",
                "username": username,
                "players": room.active_players,
            },
        )


async def websocket_sender(
    websocket: WebSocket, room_id: str, manager: RoomManager
) -> None:
    async with manager.broadcast.subscribe(channel=f"chatroom_{room_id}") as subscriber:
        async for event in subscriber:
            await websocket.send_text(event.message)


@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_id: str,
    token: Optional[str] = Query(None),
    session: Session = Depends(get_session),
) -> None:
    manager = get_room_manager()

    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        current_user = get_user_by_username(session, username=username)
        if not current_user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        user_id = str(current_user.id)

    except jwt.InvalidTokenError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    try:
        messages = session.exec(
            select(Message)
            .where(Message.room_id == int(room_id))
            .order_by(Message.created_at.desc())
            .limit(50)
        ).all()

        for msg in reversed(messages):
            await websocket.send_json(
                {
                    "type": "history",
                    "username": msg.username,
                    "message": msg.message,
                    "timestamp": msg.created_at.isoformat(),
                }
            )

        async with anyio.create_task_group() as task_group:

            async def run_receiver() -> None:
                await websocket_receiver(
                    websocket=websocket,
                    room_id=room_id,
                    user_id=user_id,
                    username=username,
                    session=session,
                    manager=manager,
                )
                task_group.cancel_scope.cancel()

            task_group.start_soon(run_receiver)
            await websocket_sender(
                websocket=websocket, room_id=room_id, manager=manager
            )

    except Exception as e:
        log.error(f"WebSocket error for user {username}: {e}")
        raise


@router.get("/rooms/{room_id}/players")
async def get_room_players(
    room_id: str, session: Session = Depends(get_session)
) -> Dict:
    manager = get_room_manager()
    room = await manager.get_or_create_room(room_id, session)

    return {
        "room_id": room_id,
        "players": room.active_players,
        "max_players": room.max_players,
        "game_active": room.game_active,
    }


@router.post("/rooms/{room_id}/kick/{username}")
async def kick_player(
    room_id: str, username: str, session: Session = Depends(get_session)
) -> Dict:
    manager = get_room_manager()
    room = manager.rooms.get(room_id)

    if not room:
        raise HTTPException(404, detail="Room not found")

    if username not in room._connections:
        raise HTTPException(404, detail="Player not found")

    await room._connections[username].close()

    return {"message": f"Player {username} kicked from room {room_id}"}


async def init_room_manager(broadcast: Broadcast):
    global room_manager
    room_manager = RoomManager(broadcast)
