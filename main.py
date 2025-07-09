from collections import namedtuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import json
import uuid
from rps import Game, FixedActionPlayer, RandomActionPlayer

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------

class PlayerCreateRequest(BaseModel):
    player_name: str


class PlayerResponse(BaseModel):
    player_id: str
    player_name: str


class RoomCreateRequest(BaseModel):
    room_name: str
    max_players: str
    number_of_actions: str
    player_id: str


class RoomJoinRequest(BaseModel):
    room_id: str
    player_id: str


class RoomResponse(BaseModel):
    id: str
    name: str
    player_count: int
    max_players: int
    number_of_actions: int


# -----------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------


class Player:
    def __init__(self, player_id: str, name: str):
        self.id = player_id
        self.name = name
        self.current_room: Optional[str] = None
        self.websocket: Optional[WebSocket] = None


PlayerAction = namedtuple("PlayerAction", ["player_id", "message_id", "action"])
RoomPlayer = namedtuple("RoomPlayer", ["player", "locked"])


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


manager = GameManager()


# -----------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------


@app.post("/api/login", response_model=PlayerResponse)
async def login(request: PlayerCreateRequest):
    player_id = manager.create_player(request.player_name)
    return PlayerResponse(player_id=player_id, player_name=request.player_name)


@app.get("/api/player/{player_id}")
async def get_player(player_id: str):
    player = manager.get_player(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return {
        "player_id": player.id,
        "player_name": player.name,
        "current_room": player.current_room,
    }


@app.post("/api/rooms/create")
async def create_room(request: RoomCreateRequest):
    if request.number_of_actions is None or request.number_of_actions == "":
        request.number_of_actions = str(3)
    if request.max_players is None or request.max_players == "":
        request.max_players = str(10)

    room_id = manager.create_room(
        request.room_name, request.max_players, request.number_of_actions
    )

    if manager.join_room(request.player_id, room_id):
        return {"room_id": room_id, "success": True}
    else:
        raise HTTPException(status_code=400, detail="Failed to create room")


@app.post("/api/rooms/join")
async def join_room(request: RoomJoinRequest):
    if manager.join_room(request.player_id, request.room_id):
        room = manager.get_room(request.room_id)
        return {
            "success": True,
            "room": {
                "id": room.id,
                "name": room.name,
                "number_of_actions": room.number_of_actions,
                "player_count": len(room.players),
                "max_players": room.max_players,
            },
        }
    else:
        raise HTTPException(status_code=400, detail="Failed to join room")


@app.post("/api/rooms/leave")
async def leave_room(player_id: str):
    manager.leave_room(player_id)
    return {"success": True}


@app.get("/api/rooms", response_model=List[RoomResponse])
async def get_rooms():
    rooms_data = []
    for room in manager.rooms.values():
        rooms_data.append(
            RoomResponse(
                id=room.id,
                name=room.name,
                player_count=len(room.players),
                max_players=room.max_players,
                number_of_actions=room.number_of_actions,
            )
        )
    return rooms_data


@app.get("/api/rooms/{room_id}")
async def get_room_details(room_id: str):
    room = manager.get_room(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    return {
        "id": room.id,
        "name": room.name,
        "player_count": len(room.players),
        "max_players": room.max_players,
        "players": [{"id": p.id, "name": p.name} for p in room.players.values()],
        "messages": room.messages[-50:],
    }


# -----------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------


@app.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):
    await websocket.accept()

    player = manager.get_player(player_id)
    room = manager.get_room(room_id)

    if player and room and player_id in room.players:
        # Update player's websocket reference
        room_player = room.players[player_id]
        room.players[player_id] = RoomPlayer(
            player=room_player.player, locked=room_player.locked
        )
        player.websocket = websocket

    if not player or not room or player_id not in room.players:
        if room:
            print("room.players:", list(room.players.keys()))
        print("player_id:", player_id)
        await websocket.close()
        return

    player.websocket = websocket

    await websocket.send_text(
        json.dumps(
            {
                "type": "room_info",
                "room_name": room.name,
                "number_of_actions": room.number_of_actions,
                "players": [{"id": p.player.id, "name": p.player.name, "locked": p.locked}
                            for p in room.players.values()],
            }
        )
    )

    if room.messages:
        await websocket.send_text(
            json.dumps({"type": "message_history", "messages": room.messages[-20:]})
        )

    await manager.broadcast_to_room(
        room_id,
        {"type": "system", "message": f"{player.name} joined the room"},
        exclude_player=player_id,
    )

    await manager.broadcast_to_room(
        room_id,
        {
            "type": "players_update",
            "players": [{"id": p.player.id, "name": p.player.name, "locked": p.locked}
                        for p in room.players.values()]
        },
    )

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)

            if message_data["type"] == "chat":
                message_obj = {
                    "id": str(uuid.uuid4())[:8],
                    "player_id": player_id,
                    "player_name": player.name,
                    "message": message_data["message"],
                    "timestamp": str(uuid.uuid4()),
                }

                room.messages.append(message_obj)

                await manager.broadcast_to_room(
                    room_id, {"type": "chat", **message_obj}
                )

            if message_data["type"] == "play":
                player_action = int(message_data["message"])
                message_id = str(uuid.uuid4())[:8]
                is_ready_message = "is ready"
                message_obj = {
                    "id": message_id,
                    "player_id": player_id,
                    "player_name": player.name,
                    "message": is_ready_message,
                    "timestamp": str(uuid.uuid4()),
                }

                await manager.broadcast_to_room(
                    room_id, {"type": "chat", **message_obj}
                )

                room.messages.append(message_obj)
                player_action_obj = PlayerAction(player_id, message_id, player_action)

                if room.round_number not in room.game_rounds:
                    room.game_rounds[room.round_number] = []

                room.game_rounds[room.round_number].append(player_action_obj)

                # Update player's locked status
                if player_id in room.players:
                    room.players[player_id] = RoomPlayer(player=room.players[player_id].player, locked=True)

                if len(room.game_rounds[room.round_number]) == room.max_players:
                    # play the round
                    all_players = []
                    for player_action in room.game_rounds[room.round_number]:
                        player = FixedActionPlayer(player_action.player_id, player_action.action)
                        all_players.append(player)

                    game = Game(all_players, room.number_of_actions)
                    result = game.play_round()
                    print("result ", [p.name for p in result])

                    result_list = [p.name for p in result]

                    # Reset locked status for all players
                    for p_id in room.players:
                        room.players[p_id] = RoomPlayer(player=room.players[p_id].player, locked=False)

                    game_message_obj = {
                        "id": str(uuid.uuid4())[:8],
                        "player_id": str(uuid.uuid4())[:8],
                        "player_name": "Game",
                        "message": f"Round {room.round_number} result: {result_list}",
                        "timestamp": str(uuid.uuid4()),
                    }

                    await manager.broadcast_to_room(
                        room_id, {"type": "chat", **game_message_obj}
                    )

                    room.game_round_results[room.round_number] = result_list

                    # Reset game_rounds for the next round
                    room.round_number += 1
                    room.game_rounds[room.round_number] = []


    except WebSocketDisconnect:
        if player:
            player.websocket = None

            await manager.broadcast_to_room(
                room_id,
                {"type": "system", "message": f"{player.name} left the room"},
                exclude_player=player_id,
            )

            manager.leave_room(player_id)

            room = manager.get_room(room_id)
            if room:
                await manager.broadcast_to_room(
                    room_id,
                    {
                        "type": "players_update",
                        "players": [
                            {"id": p.player.id, "name": p.player.name, "locked": p.locked}
                            for p in room.players.values()
                        ],
                    },
                )


# -----------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------
# -----------------------------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
