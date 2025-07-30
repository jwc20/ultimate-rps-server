import json
import logging
from datetime import datetime, timezone
from sqlmodel import Session
from fastapi import WebSocket
from fastapi.websockets import WebSocketState

from ..models import Message
from ..game import RoomManager

log = logging.getLogger(__name__)


class WebSocketHandler:
    """Handles WebSocket message processing and communication"""

    @staticmethod
    async def handle_messages(
            websocket: WebSocket,
            room_id: str,
            user_id: str,
            username: str,
            session: Session,
            manager: RoomManager,
    ) -> None:
        """Main message handling loop for WebSocket connections"""
        room = await manager.get_or_create_room(room_id, session)

        try:
            await room.add_player(user_id, username, websocket, session)
            
            bot_names = [bot for bot in room.bots]
            
            await manager.broadcast_to_room(
                room_id,
                {
                    "type": "player_joined",
                    "username": username,
                    "players": room.active_players + bot_names,
                },
            )

            async for message in websocket.iter_text():
                try:
                    msg_data = json.loads(message)
                    await WebSocketHandler._process_message(
                        msg_data, websocket, room_id, username, session, manager, room
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

    @staticmethod
    async def _process_message(
            msg_data: dict,
            websocket: WebSocket,
            room_id: str,
            username: str,
            session: Session,
            manager: RoomManager,
            room,
    ) -> None:
        """Process individual WebSocket messages based on type"""
        msg_type = msg_data.get("type")

        if msg_type == "play":
            await WebSocketHandler._handle_play_action(
                msg_data, room_id, username, manager
            )
        elif msg_type == "start_game":
            await WebSocketHandler._handle_start_game(room_id, manager, room)
        elif msg_type == "kick_player":
            await WebSocketHandler._handle_kick_player(
                msg_data, websocket, room_id, manager, room
            )
        elif msg_type == "reset_game":
            await WebSocketHandler._handle_reset_game(room_id, manager, room)
        elif msg_type == "message":
            await WebSocketHandler._handle_chat_message(
                msg_data, room_id, username, session, manager
            )

    @staticmethod
    async def _handle_play_action(
            msg_data: dict, room_id: str, username: str, manager: RoomManager
    ) -> None:
        """Handle game play actions"""
        action = int(msg_data.get("message", 0))
        await manager.handle_player_action(room_id, username, action)

    @staticmethod
    async def _handle_start_game(room_id: str, manager: RoomManager, room) -> None:
        """Handle game start requests"""
        if room.start_game():
            await manager.broadcast_to_room(
                room_id,
                {"type": "game_started", "players": room.active_players},
            )

    @staticmethod
    async def _handle_kick_player(
            msg_data: dict,
            websocket: WebSocket,
            room_id: str,
            manager: RoomManager,
            room,
    ) -> None:
        """Handle player kick requests"""
        host_username = msg_data.get("username", "")
        target_username = msg_data.get("target", "")

        if host_username not in room._player_info:
            await websocket.send_json({"type": "error", "message": "Unauthorized"})
            return

        if target_username not in room._connections:
            await websocket.send_json({"type": "error", "message": "Player not found"})
            return

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

    @staticmethod
    async def _handle_reset_game(room_id: str, manager: RoomManager, room) -> None:
        """Handle game reset requests"""
        if room.game_over:
            room.reset_game()
            print(room)
            await manager.broadcast_to_room(
                room_id,
                {
                    "type": "game_reset",
                    "players": room.active_players,
                    "kicked_players": room.kicked_players,
                    "game_number": room.game_number,
                    "game_round": room.round_number,
                },
            )

    @staticmethod
    async def _handle_chat_message(
            msg_data: dict,
            room_id: str,
            username: str,
            session: Session,
            manager: RoomManager,
    ) -> None:
        """Handle chat messages"""
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

    @staticmethod
    async def broadcast_to_client(
            websocket: WebSocket, room_id: str, manager: RoomManager
    ) -> None:
        """Handle broadcasting messages to WebSocket client"""
        async with manager.broadcast.subscribe(channel=f"chatroom_{room_id}") as subscriber:
            async for event in subscriber:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text(event.message)