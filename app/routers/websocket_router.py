import logging
from sqlmodel import Session, select
import jwt
import anyio
from broadcaster import Broadcast

from ..models import Message
from ..config import SECRET_KEY, ALGORITHM
from ..database import get_session
from .auth import get_user_by_username
from .websocket_handler import WebSocketHandler

from fastapi import APIRouter, Depends, Query, WebSocket, status
from ..game import RoomManager

log = logging.getLogger(__name__)
router = APIRouter()

game_manager: RoomManager | None = None


def get_room_manager() -> RoomManager:
    """Dependency to get the game manager instance"""
    if game_manager is None:
        raise RuntimeError("Game manager not initialized")
    return game_manager


async def authenticate_websocket(
        websocket: WebSocket, token: str | None, session: Session
) -> tuple[str, str] | None:
    """Authenticate WebSocket connection and return user_id and username"""
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return None

        current_user = get_user_by_username(session, username=username)
        if not current_user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return None

        return str(current_user.id), username

    except jwt.InvalidTokenError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None


async def send_message_history(websocket: WebSocket, room_id: str, session: Session) -> None:
    """Send recent message history to newly connected client"""
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


@router.websocket("/ws/{room_id}")
async def websocket_endpoint(
        websocket: WebSocket,
        room_id: str,
        token: str | None = Query(None),
        session: Session = Depends(get_session),
) -> None:
    """Main WebSocket endpoint for room connections"""
    manager = get_room_manager()

    # Authenticate the WebSocket connection
    auth_result = await authenticate_websocket(websocket, token, session)
    if not auth_result:
        return

    user_id, username = auth_result
    await websocket.accept()

    try:
        # Send message history to the client
        await send_message_history(websocket, room_id, session)

        # Start concurrent tasks for message handling and broadcasting
        async with anyio.create_task_group() as task_group:

            async def run_message_handler() -> None:
                """Task to handle incoming WebSocket messages"""
                await WebSocketHandler.handle_messages(
                    websocket=websocket,
                    room_id=room_id,
                    user_id=user_id,
                    username=username,
                    session=session,
                    manager=manager,
                )
                task_group.cancel_scope.cancel()

            # Start message handler task
            task_group.start_soon(run_message_handler)

            # Handle outgoing broadcasts to this client
            await WebSocketHandler.broadcast_to_client(
                websocket=websocket, room_id=room_id, manager=manager
            )

    except Exception as e:
        log.error(f"WebSocket error for user {username}: {e}")
        raise


async def init_room_manager(broadcast: Broadcast) -> None:
    """Initialize the global room manager instance"""
    global game_manager
    game_manager = RoomManager(broadcast)