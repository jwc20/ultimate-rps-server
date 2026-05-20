from datetime import datetime, timezone
from fastapi import APIRouter

from app.auth import CurrentUser
from app.database import SessionDep
from app.schemas import RoomCreate

router = APIRouter()


def _row_to_dict(row) -> dict:
    return dict(row)


@router.post("/create-room")
async def create_room(room: RoomCreate, conn: SessionDep, current_user: CurrentUser):
    current_user_id = current_user.id
    created_at = datetime.now(timezone.utc).isoformat()
    cursor = conn.execute(
        """INSERT INTO room (room_name, max_players, number_of_actions, created_by, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (room.room_name, room.max_players, room.number_of_actions, current_user_id, created_at),
    )
    room_id = cursor.lastrowid
    row = conn.execute("SELECT * FROM room WHERE id = ?", (room_id,)).fetchone()
    return _row_to_dict(row)


@router.get("/rooms")
async def get_rooms(conn: SessionDep):
    cursor = conn.execute("SELECT * FROM room")
    return [_row_to_dict(row) for row in cursor.fetchall()]


@router.get("/room/{room_id}")
async def get_room(room_id: int, conn: SessionDep):
    cursor = conn.execute("SELECT * FROM room WHERE id = ?", (room_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    return _row_to_dict(row)