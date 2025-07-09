import json
from typing import Dict, Optional
from ..models.game import Player, Room, RoomPlayer
import uuid


class GameManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self.players: Dict[str, Player] = {}

    def create_room(self, name: str, max_players: str, number_of_actions: str) -> str:
        room_id = str(uuid.uuid4())[:8]
        max_players = int(max_players)
        number_of_actions = int(number_of_actions)
        self.rooms[room_id] = Room(room_id, name, max_players, number_of_actions)
        return room_id

    def get_room(self, room_id: str) -> Optional[Room]:
        return self.rooms.get(room_id)

    def create_player(self, name: str) -> str:
        player_id = str(uuid.uuid4())[:8]
        self.players[player_id] = Player(player_id, name)
        return player_id

    def get_player(self, player_id: str) -> Optional[Player]:
        return self.players.get(player_id)

    def join_room(self, player_id: str, room_id: str) -> bool:
        player = self.get_player(player_id)
        room = self.get_room(room_id)

        if not player or not room:
            return False

        if len(room.players) >= int(room.max_players):
            return False

        if player.current_room:
            self.leave_room(player_id)

        # room.players[player_id] = player
        room.players[player_id] = RoomPlayer(player=player, locked=False)
        player.current_room = room_id
        return True

    def leave_room(self, player_id: str):
        player = self.players.get(player_id)
        if not player or not player.current_room:
            return

        room = self.rooms.get(player.current_room)
        if room and player_id in room.players:
            del room.players[player_id]

        player.current_room = None

    async def broadcast_to_room(
            self, room_id: str, message: dict, exclude_player: str = None
    ):
        room = self.get_room(room_id)
        if not room:
            return

        message_json = json.dumps(message)

        for player_id, player in room.players.items():
            if player_id != exclude_player and player.player.websocket:
                try:
                    await player.player.websocket.send_text(message_json)
                except:
                    pass  # Handle disconnected websockets
