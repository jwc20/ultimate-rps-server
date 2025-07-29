import json
import logging

from sqlmodel import Session, select
import jwt
import anyio
from broadcaster import Broadcast

from ..models import Room, Message
from ..config import SECRET_KEY, ALGORITHM
from ..database import get_session
from .auth import get_user_by_username

from fastapi import APIRouter, Depends, Query, WebSocket, status, HTTPException, Response
from fastapi.websockets import WebSocketState
from datetime import datetime, timezone

from ..game import GameManager


log = logging.getLogger(__name__)
router = APIRouter()

game_manager: GameManager | None = None


def get_room_manager() -> GameManager:
    if game_manager is None:
        raise RuntimeError("Game manager not initialized")
    return game_manager


async def websocket_receiver(
        websocket: WebSocket,
        room_id: str,
        user_id: str,
        username: str,
        session: Session,
        manager: GameManager,
) -> None:
    room = await manager.get_or_create_room(room_id, session)

    try:
        await room.add_player(user_id, username, websocket, session)
        
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

                elif msg_type == "kick_player":
                    host_username = msg_data.get("username", "")
                    target_username = msg_data.get("target", "")
                    
                    if host_username not in room._player_info:
                        await websocket.send_json({"type": "error", "message": "Unauthorized"})
                        continue

                    if target_username not in room._connections:
                        await websocket.send_json({"type": "error", "message": "Player not found"})
                        continue

                    target_ws = room._connections[target_username]
                    await target_ws.close(code=4001, reason="Kicked by host")
                    room._kicked_players.add(target_username)

                    await manager.broadcast_to_room(
                        room_id,
                        {
                            "type": "kick_player",
                            "host": host_username,
                            "kick_player": target_username,
                            "players": room.active_players,
                            "kicked_players": room.kicked_players,
                        },
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
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )

            except (json.JSONDecodeError, ValueError) as e:
                log.error(f"Error processing message from {username}: {e}")
                await websocket.send_json(
                    {"type": "error", "message": "Invalid message format"}
                )

    finally:
        await room.remove_player(username, session)
        await manager.broadcast_to_room(
            room_id,
            {
                "type": "player_left",
                "username": username,
                "players": room.active_players,
            },
        )


async def websocket_sender(
        websocket: WebSocket, room_id: str, manager: GameManager
) -> None:
    async with manager.broadcast.subscribe(channel=f"chatroom_{room_id}") as subscriber:
        async for event in subscriber:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_text(event.message)


@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
        websocket: WebSocket,
        room_id: str,
        token: str | None = Query(None),
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


async def init_room_manager(broadcast: Broadcast):
    global game_manager
    game_manager = GameManager(broadcast)
