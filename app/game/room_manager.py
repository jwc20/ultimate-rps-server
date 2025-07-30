from . import GameState
from broadcaster import Broadcast
from sqlmodel import Session, select
from ..models import Room
from rps import RandomActionPlayer

import json 
import logging 

log = logging.getLogger(__name__)


class RoomManager:
    def __init__(self, broadcast: Broadcast):
        self.broadcast = broadcast
        self.rooms: dict[str, GameState] = {}

    async def get_or_create_room(self, room_id: str, session: Session) -> GameState:
        if room_id not in self.rooms:
            room = session.exec(select(Room).where(Room.id == int(room_id))).first()
            if not room:
                raise ValueError(f"Room {room_id} not found in database")
            
            bots = list()
            for i in range(room.number_of_bots):
                bot_name = f"bot{i}"
                bots.append(bot_name)

            self.rooms[room_id] = GameState(
                room_id=int(room_id),
                max_players=room.max_players,
                number_of_actions=room.number_of_actions,
                number_of_bots=room.number_of_bots,
                bots=bots,
            )
        return self.rooms[room_id]

    async def broadcast_to_room(self, room_id: str, message: dict) -> None:
        await self.broadcast.publish(
            channel=f"chatroom_{room_id}", message=json.dumps(message)
        )

    async def handle_player_action(
        self, room_id: str, username: str, action: int
    ) -> None:
        room = self.rooms.get(room_id)
        if not room:
            return

        if await room.submit_action(username, action):
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
                    results = await room.process_round()
                    await self.broadcast_to_room(
                        room_id, {"type": "round_complete", **results}
                    )
                except Exception as e:
                    log.error(f"Error processing round: {e}")
                    await self.broadcast_to_room(
                        room_id, {"type": "error", "message": "Failed to process round"}
                    )