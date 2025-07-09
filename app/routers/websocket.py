import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from rps import FixedActionPlayer, Game

from ..models.game import RoomPlayer, PlayerAction
from ..dependencies import GameManagerDep
import json

router = APIRouter()


@router.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: str, manager: GameManagerDep):
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
