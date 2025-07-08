from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Dict, List, Optional
import json
import uuid
from rps import Game, FixedActionPlayer, RandomActionPlayer

app = FastAPI()


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

    def create_room(self, name: str, number_of_actions: int = 3) -> str:
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

# HTML Templates
lobby_html = """
<!DOCTYPE html>
<html>
<head>
    <title>Game Lobby</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        .room-list { border: 1px solid #ccc; padding: 15px; margin: 10px 0; border-radius: 5px; }
        .room-item { border: 1px solid #ddd; margin: 10px 0; padding: 10px; border-radius: 3px; }
        .button { background: #007cba; color: white; padding: 10px 15px; border: none; border-radius: 3px; cursor: pointer; }
        .button:hover { background: #005a8a; }
        input[type="text"] { padding: 8px; margin: 5px; border: 1px solid #ccc; border-radius: 3px; }
        .player-info { background: #f5f5f5; padding: 10px; border-radius: 5px; margin-bottom: 20px; }
    </style>
</head>
<body>
    <h1>🎮 Game Lobby</h1>

    <div class="player-info">
        <h3>Player: <span id="player-name"></span></h3>
        <p>Player ID: <span id="player-id"></span></p>
    </div>

    <div class="room-list">
        <h2>Create New Room</h2>
        <form action="/create_room" method="post">
            <input type="hidden" name="player_id" id="create-player-id">
            <input type="text" name="room_name" placeholder="Room Name" required>
            <input type="text" name="number_of_actions" placeholder="Number of Actions" required>
            <button type="submit" class="button">Create Room</button>
        </form>
    </div>

    <div class="room-list">
        <h2>Available Rooms</h2>
        <div id="rooms-container">
            <p>Loading rooms...</p>
        </div>
        <button onclick="loadRooms()" class="button">Refresh Rooms</button>
    </div>

    <script>
        // Get player info from URL parameters
        const urlParams = new URLSearchParams(window.location.search);
        const playerId = urlParams.get('player_id');
        const playerName = urlParams.get('player_name');

        if (!playerId || !playerName) {
            // Redirect to login if no player info
            window.location.href = '/login';
        }

        document.getElementById('player-name').textContent = playerName;
        document.getElementById('player-id').textContent = playerId;
        document.getElementById('create-player-id').value = playerId;

        async function loadRooms() {
            try {
                const response = await fetch('/api/rooms');
                const rooms = await response.json();
                const container = document.getElementById('rooms-container');

                if (rooms.length === 0) {
                    container.innerHTML = '<p>No rooms available. Create one!</p>';
                    return;
                }

                container.innerHTML = rooms.map(room => `
                    <div class="room-item">
                        <h4>${room.name}</h4>
                        <p>Players: ${room.player_count}/${room.max_players}</p>
                        <p>Room ID: ${room.id}</p>
                        <form action="/join_room" method="post" style="display: inline;">
                            <input type="hidden" name="player_id" value="${playerId}">
                            <input type="hidden" name="room_id" value="${room.id}">
                            <button type="submit" class="button" ${room.player_count >= room.max_players ? 'disabled' : ''}>
                                ${room.player_count >= room.max_players ? 'Room Full' : 'Join Room'}
                            </button>
                        </form>
                    </div>
                `).join('');
            } catch (error) {
                console.error('Error loading rooms:', error);
            }
        }

        // Load rooms on page load
        loadRooms();

        // Auto-refresh rooms every 5 seconds
        setInterval(loadRooms, 5000);
    </script>
</body>
</html>
"""

login_html = """
<!DOCTYPE html>
<html>
<head>
    <title>Player Login</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 400px; margin: 100px auto; padding: 20px; text-align: center; }
        .login-form { border: 1px solid #ccc; padding: 30px; border-radius: 10px; background: #f9f9f9; }
        input[type="text"] { width: 100%; padding: 12px; margin: 10px 0; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; }
        .button { background: #007cba; color: white; padding: 12px 20px; border: none; border-radius: 5px; cursor: pointer; width: 100%; font-size: 16px; }
        .button:hover { background: #005a8a; }
    </style>
</head>
<body>
    <div class="login-form">
        <h1>🎮 Enter Game</h1>
        <p>Choose your player name to start playing!</p>
        <form action="/login" method="post">
            <input type="text" name="player_name" placeholder="Your Player Name" required maxlength="20">
            <button type="submit" class="button">Enter Lobby</button>
        </form>
    </div>
</body>
</html>
"""

room_html = """
<!DOCTYPE html>
<html>
<head>
    <title>Game Room</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        .room-header { background: #007cba; color: white; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
        .game-area { display: flex; gap: 20px; }
        .chat-area { flex: 2; }
        .players-area { flex: 1; background: #f5f5f5; padding: 15px; border-radius: 5px; }
        .messages { border: 1px solid #ccc; height: 300px; overflow-y: auto; padding: 10px; margin-bottom: 10px; background: white; }
        .message { margin: 5px 0; padding: 5px; border-radius: 3px; }
        .message.own { background: #e3f2fd; }
        .message.system { background: #fff3cd; font-style: italic; }
        .message-form { display: flex; gap: 10px; }
        .message-input { flex: 1; padding: 8px; border: 1px solid #ccc; border-radius: 3px; }
        .button { background: #007cba; color: white; padding: 8px 15px; border: none; border-radius: 3px; cursor: pointer; }
        .button:hover { background: #005a8a; }
        .leave-button { background: #dc3545; }
        .leave-button:hover { background: #c82333; }
        .player-item { padding: 5px; margin: 2px 0; background: white; border-radius: 3px; }
    </style>
</head>
<body>
    <div class="room-header">
        <h1 id="room-name">Room</h1>
        <p>Player: <span id="player-name"></span> | Room ID: <span id="room-id"></span></p>
        <a href="/lobby?player_id={{PLAYER_ID}}&player_name={{PLAYER_NAME}}" class="button leave-button">Leave Room</a>
    </div>

    <div class="game-area">
        <div class="chat-area">
            <h3>💬 Game Chat</h3>
            <div id="messages" class="messages"></div>
            <form class="message-form" onsubmit="sendMessage(event)">
                <input type="text" id="messageText" class="message-input" placeholder="Type your message..." autocomplete="off" required/>
                <button type="submit" class="button">Send</button>
            </form>
        </div>

        <div class="players-area">
            <h3>👥 Players in Room</h3>
            <div id="players-list"></div>
        </div>
    </div>

    <script>
        const urlParams = new URLSearchParams(window.location.search);
        const playerId = '{{PLAYER_ID}}';
        const playerName = '{{PLAYER_NAME}}';
        const roomId = '{{ROOM_ID}}';

        document.getElementById('player-name').textContent = playerName;
        document.getElementById('room-id').textContent = roomId;

        const ws = new WebSocket(`ws://localhost:8000/ws/${roomId}/${playerId}`);

        ws.onmessage = function(event) {
            const data = JSON.parse(event.data);
            handleMessage(data);
        };

        ws.onopen = function(event) {
            console.log('Connected to room');
        };

        ws.onclose = function(event) {
            console.log('Disconnected from room');
        };

        function handleMessage(data) {
            const messagesDiv = document.getElementById('messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = 'message';

            if (data.type === 'chat') {
                if (data.player_id === playerId) {
                    messageDiv.className += ' own';
                }
                messageDiv.innerHTML = `<strong>${data.player_name}:</strong> ${data.message}`;
            } else if (data.type === 'system') {
                messageDiv.className += ' system';
                messageDiv.textContent = data.message;
            } else if (data.type === 'room_info') {
                document.getElementById('room-name').textContent = data.room_name;
                updatePlayersList(data.players);
                return;
            } else if (data.type === 'players_update') {
                updatePlayersList(data.players);
                return;
            }

            messagesDiv.appendChild(messageDiv);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function updatePlayersList(players) {
            const playersDiv = document.getElementById('players-list');
            playersDiv.innerHTML = players.map(player => 
                `<div class="player-item">${player.name} ${player.id === playerId ? '(You)' : ''}</div>`
            ).join('');
        }

        function sendMessage(event) {
            event.preventDefault();
            const input = document.getElementById('messageText');
            if (input.value.trim()) {
                ws.send(JSON.stringify({
                    type: 'chat',
                    message: input.value
                }));
                input.value = '';
            }
        }

        // Auto-focus message input
        document.getElementById('messageText').focus();
    </script>
</body>
</html>
"""


# Routes
@app.get("/")
async def root():
    return RedirectResponse(url="/login")


@app.get("/login")
async def login_page():
    return HTMLResponse(login_html)


@app.post("/login")
async def login(player_name: str = Form(...)):
    player_id = manager.create_player(player_name)
    return RedirectResponse(url=f"/lobby?player_id={player_id}&player_name={player_name}", status_code=303)


@app.get("/lobby")
async def lobby(player_id: str, player_name: str):
    return HTMLResponse(lobby_html)


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

    html_content = room_html.replace('{{PLAYER_ID}}', player_id).replace('{{PLAYER_NAME}}', player_name).replace(
        '{{ROOM_ID}}', room_id)
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
