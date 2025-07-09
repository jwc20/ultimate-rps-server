from typing import Annotated
from fastapi import Depends
from .services.game_manager import GameManager

# singleton pattern
_manager_instance = None

def get_game_manager() -> GameManager:
    """Get the singleton GameManager instance."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = GameManager()
    return _manager_instance

# convenience type alias for dependency injection
GameManagerDep = Annotated[GameManager, Depends(get_game_manager)]