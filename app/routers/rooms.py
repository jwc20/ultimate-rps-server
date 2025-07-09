from fastapi import APIRouter, HTTPException
from typing import List
from ..models.schemas import RoomCreateRequest, RoomResponse, RoomJoinRequest
from ..dependencies import GameManagerDep

router = APIRouter()

@router.post("/rooms/create")
async def create_room(request: RoomCreateRequest, manager: GameManagerDep):
    if request.number_of_actions is None or request.number_of_actions == "":
        request.number_of_actions = str(3)
    if request.max_players is None or request.max_players == "":
        request.max_players = str(2)

    room_id = manager.create_room(
        request.room_name, request.max_players, request.number_of_actions
    )

    if manager.join_room(request.player_id, room_id):
        return {"room_id": room_id, "success": True}
    else:
        raise HTTPException(status_code=400, detail="Failed to create room")


@router.post("/rooms/join")
async def join_room(request: RoomJoinRequest, manager: GameManagerDep):
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


@router.post("/rooms/leave")
async def leave_room(player_id: str, manager: GameManagerDep):
    manager.leave_room(player_id)
    return {"success": True}


@router.get("/rooms", response_model=List[RoomResponse])
async def get_rooms(manager: GameManagerDep):
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


@router.get("/rooms/{room_id}")
async def get_room_details(room_id: str, manager: GameManagerDep):
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