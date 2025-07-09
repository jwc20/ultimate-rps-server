from fastapi import APIRouter, HTTPException
from ..models.schemas import PlayerCreateRequest, PlayerResponse
from ..dependencies import GameManagerDep

router = APIRouter()

@router.post("/login", response_model=PlayerResponse)
async def login(request: PlayerCreateRequest, manager: GameManagerDep):
    player_id = manager.create_player(request.player_name)
    return PlayerResponse(player_id=player_id, player_name=request.player_name)

@router.get("/player/{player_id}")
async def get_player(player_id: str, manager: GameManagerDep):
    player = manager.get_player(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return {
        "player_id": player.id,
        "player_name": player.name,
        "current_room": player.current_room,
    }