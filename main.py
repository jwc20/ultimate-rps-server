from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import json
import uuid
from rps import Game, FixedActionPlayer, RandomActionPlayer

app = FastAPI()

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response Models
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


# Data Models
class Player:
    def __init__(self, player_id: str, name: str):
        self.id = player_id
        self.name = name
        self.current_room: Optional[str] = None
        self.websocket: Optional[WebSocket] = None


class Room:
    def __init__(self, room_id: str, name: str, max_players: int, number_of_actions: int):
        self.id = room_id
        self.name = name
        self.number_of_actions = number_of_actions
        self.max_players = max_players
        self.players: Dict[str, Player] = {}
        self.messages: List[dict] = []


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

        # Leave current room if in one
        if player.current_room:
            self.leave_room(player_id)

        # Join new room
        room.players[player_id] = player
        player.current_room = room_id
        return True

    def leave_room(self, player_id: str):
        player = self.get_player(player_id)
        if not player or not player.current_room:
            return

        room = self.get_room(player.current_room)
        if room and player_id in room.players:
            del room.players[player_id]

        player.current_room = None

    async def broadcast_to_room(self, room_id: str, message: dict, exclude_player: str = None):
        room = self.get_room(room_id)
        if not room:
            return

        message_json = json.dumps(message)
        for player_id, player in room.players.items():
            if player_id != exclude_player and player.websocket:
                try:
                    await player.websocket.send_text(message_json)
                except:
                    pass  # Handle disconnected websockets


manager = GameManager()


# API Routes
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
        "current_room": player.current_room
    }


@app.post("/api/rooms/create")
async def create_room(request: RoomCreateRequest):
    print(request)
    room_id = manager.create_room(request.room_name, request.max_players, request.number_of_actions)
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
                "max_players": room.max_players
            }
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
        rooms_data.append(RoomResponse(
            id=room.id,
            name=room.name,
            player_count=len(room.players),
            max_players=room.max_players,
            number_of_actions=room.number_of_actions
        ))
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
        "messages": room.messages[-50:]  # Last 50 messages
    }


@app.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):
    await websocket.accept()

    player = manager.get_player(player_id)
    room = manager.get_room(room_id)

    if not player or not room or player_id not in room.players:
        print("❌ Closing WebSocket: invalid state")
        print("player:", player)
        print("room:", room)
        if room:
            print("room.players:", list(room.players.keys()))
        print("player_id:", player_id)
        await websocket.close()
        return

    player.websocket = websocket

    # Send room info and current players
    await websocket.send_text(json.dumps({
        "type": "room_info",
        "room_name": room.name,
        "number_of_actions": room.number_of_actions,
        "players": [{"id": p.id, "name": p.name} for p in room.players.values()]
    }))

    # Send recent messages
    if room.messages:
        await websocket.send_text(json.dumps({
            "type": "message_history",
            "messages": room.messages[-20:]  # Last 20 messages
        }))

    # Notify others that player joined
    await manager.broadcast_to_room(room_id, {
        "type": "system",
        "message": f"{player.name} joined the room"
    }, exclude_player=player_id)

    # Send updated players list to all
    await manager.broadcast_to_room(room_id, {
        "type": "players_update",
        "players": [{"id": p.id, "name": p.name} for p in room.players.values()]
    })

    try:
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)

            if message_data["type"] == "chat":
                # Create message object
                message_obj = {
                    "id": str(uuid.uuid4())[:8],
                    "player_id": player_id,
                    "player_name": player.name,
                    "message": message_data["message"],
                    "timestamp": str(uuid.uuid4())  # Simple timestamp substitute
                }

                # Store message in room history
                room.messages.append(message_obj)

                # Broadcast chat message to all players in room
                await manager.broadcast_to_room(room_id, {
                    "type": "chat",
                    **message_obj
                })

    except WebSocketDisconnect:
        # Clean up player connection
        if player:
            player.websocket = None

            # Notify others that player left
            await manager.broadcast_to_room(room_id, {
                "type": "system",
                "message": f"{player.name} left the room"
            }, exclude_player=player_id)

            # Remove player from room
            manager.leave_room(player_id)

            # Send updated players list to remaining players
            room = manager.get_room(room_id)
            if room:
                await manager.broadcast_to_room(room_id, {
                    "type": "players_update",
                    "players": [{"id": p.id, "name": p.name} for p in room.players.values()]
                })


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
