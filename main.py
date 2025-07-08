from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from typing import Dict, List, Optional
import json
import uuid
import os
from pathlib import Path
from rps import Game, FixedActionPlayer, RandomActionPlayer

app = FastAPI()

# Mount static files directory (optional)
# app.mount("/static", StaticFiles(directory="static"), name="static")

# Get the directory where this script is located
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"


# Data Models
class Player:
    def __init__(self, player_id: str, name: str):
        self.id = player_id
        self.name = name
        self.current_room: Optional[str] = None
        self.websocket: Optional[WebSocket] = None


class Room:
    def __init__(self, room_id: str, name: str, max_players: int = 10):
        self.id = room_id
        self.name = name
        self.max_players = max_players
        self.players: Dict[str, Player] = {}
        self.messages: List[dict] = []


class GameManager:
    def __init__(self):
        self.rooms: Dict[str, Room] = {}
        self.players: Dict[str, Player] = {}

    def create_room(self, name: str) -> str:
        room_id = str(uuid.uuid4())[:8]
        self.rooms[room_id] = Room(room_id, name)
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

        if len(room.players) >= room.max_players:
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


# Template loading functions
def load_template(template_name: str) -> str:
    """Load HTML template from templates directory"""
    template_path = TEMPLATES_DIR / template_name
    try:
        with open(template_path, 'r', encoding='utf-8') as file:
            return file.read()
    except FileNotFoundError:
        return f"<h1>Template {template_name} not found</h1>"
    except Exception as e:
        return f"<h1>Error loading template: {str(e)}</h1>"


def render_template(template_name: str, **kwargs) -> str:
    """Load and render template with variable substitution"""
    content = load_template(template_name)

    # Simple template variable substitution
    for key, value in kwargs.items():
        placeholder = f"{{{{{key.upper()}}}}}"
        content = content.replace(placeholder, str(value))

    return content


# Routes
@app.get("/")
async def root():
    return RedirectResponse(url="/login")


@app.get("/login")
async def login_page():
    return HTMLResponse(load_template("login.html"))


@app.post("/login")
async def login(player_name: str = Form(...)):
    player_id = manager.create_player(player_name)
    return RedirectResponse(url=f"/lobby?player_id={player_id}&player_name={player_name}", status_code=303)


@app.get("/lobby")
async def lobby(player_id: str, player_name: str):
    return HTMLResponse(load_template("lobby.html"))


@app.post("/create_room")
async def create_room(room_name: str = Form(...), player_id: str = Form(...)):
    room_id = manager.create_room(room_name)
    manager.join_room(player_id, room_id)
    player = manager.get_player(player_id)
    return RedirectResponse(url=f"/room/{room_id}?player_id={player_id}&player_name={player.name}", status_code=303)


@app.post("/join_room")
async def join_room(room_id: str = Form(...), player_id: str = Form(...)):
    if manager.join_room(player_id, room_id):
        player = manager.get_player(player_id)
        return RedirectResponse(url=f"/room/{room_id}?player_id={player_id}&player_name={player.name}", status_code=303)
    else:
        return RedirectResponse(url=f"/lobby?player_id={player_id}&error=room_full", status_code=303)


@app.get("/room/{room_id}")
async def room_page(room_id: str, player_id: str, player_name: str):
    room = manager.get_room(room_id)
    if not room:
        return RedirectResponse(url=f"/lobby?player_id={player_id}&error=room_not_found")

    html_content = render_template(
        "room.html",
        player_id=player_id,
        player_name=player_name,
        room_id=room_id
    )
    return HTMLResponse(html_content)


@app.get("/api/rooms")
async def get_rooms():
    rooms_data = []
    for room in manager.rooms.values():
        rooms_data.append({
            "id": room.id,
            "name": room.name,
            "player_count": len(room.players),
            "max_players": room.max_players
        })
    return rooms_data


@app.get("/api/room/{room_id}")
async def get_room_info(room_id: str):
    room = manager.get_room(room_id)
    if not room:
        return {"error": "Room not found"}

    return {
        "id": room.id,
        "name": room.name,
        "players": [{"id": p.id, "name": p.name} for p in room.players.values()],
        "player_count": len(room.players),
        "max_players": room.max_players
    }


@app.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str):
    await websocket.accept()

    player = manager.get_player(player_id)
    room = manager.get_room(room_id)

    if not player or not room or player_id not in room.players:
        await websocket.close()
        return

    player.websocket = websocket

    # Send room info and current players
    await websocket.send_text(json.dumps({
        "type": "room_info",
        "room_name": room.name,
        "players": [{"id": p.id, "name": p.name} for p in room.players.values()]
    }))

    # Notify others that player joined
    await manager.broadcast_to_room(room_id, {
        "type": "system",
        "message": f"🎭 {player.name} joined the room"
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
                # Broadcast chat message to all players in room
                await manager.broadcast_to_room(room_id, {
                    "type": "chat",
                    "player_id": player_id,
                    "player_name": player.name,
                    "message": message_data["message"]
                })

                # Store message in room history
                room.messages.append({
                    "player_id": player_id,
                    "player_name": player.name,
                    "message": message_data["message"],
                    "timestamp": str(uuid.uuid4())  # Simple timestamp substitute
                })

    except WebSocketDisconnect:
        # Clean up player connection
        if player:
            player.websocket = None

            # Notify others that player left
            await manager.broadcast_to_room(room_id, {
                "type": "system",
                "message": f"👋 {player.name} left the room"
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


# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "rooms": len(manager.rooms),
        "players": len(manager.players)
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")