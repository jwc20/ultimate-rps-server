from fastapi import APIRouter, HTTPException
from ..models.schemas import PlayerCreateRequest, PlayerResponse
from ..dependencies import GameManagerDep

router = APIRouter()

@router.post("/login", response_model=PlayerResponse)
async def login(request: PlayerCreateRequest, manager: GameManagerDep):
    player_id = manager.create_player(request.player_name)
    return PlayerResponse(player_id=player_id, player_name=request.player_name)


@router.post("/auto-login", response_model=PlayerResponse)
async def auto_login(manager: GameManagerDep):
    """
    Create a new player with an auto-generated name.
    This is useful for completely automatic player creation.
    """
    import random

    # Generate random player name on backend
    adjectives = ['Swift', 'Brave', 'Clever', 'Mighty', 'Shadow', 'Thunder', 'Frost', 'Fire', 'Storm', 'Wild']
    nouns = ['Warrior', 'Hunter', 'Mage', 'Knight', 'Archer', 'Ninja', 'Dragon', 'Phoenix', 'Wolf', 'Eagle']

    adjective = random.choice(adjectives)
    noun = random.choice(nouns)
    number = random.randint(1, 999)

    player_name = f"{adjective}{noun}{number}"

    player_id = manager.create_player(player_name)
    return PlayerResponse(player_id=player_id, player_name=player_name)


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


@router.put("/player/{player_id}/name")
async def update_player_name(player_id: str, request: PlayerCreateRequest, manager: GameManagerDep):
    """Update player name"""
    player = manager.get_player(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Update player name
    old_name = player.name
    player.name = request.player_name

    # If player is in a room, notify other players
    if player.current_room:
        room = manager.get_room(player.current_room)
        if room:
            await manager.broadcast_to_room(
                player.current_room,
                {
                    "type": "player_name_changed",
                    "player_id": player_id,
                    "old_name": old_name,
                    "new_name": request.player_name
                },
                exclude_player=player_id
            )

    return PlayerResponse(player_id=player_id, player_name=request.player_name)
