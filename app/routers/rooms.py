from fastapi import APIRouter
from sqlmodel import select

from app.auth import CurrentUser
from app.database import SessionDep
from app.models import Room
from app.schemas import RoomCreate

router = APIRouter()


@router.post("/create-room")
async def create_room(room: RoomCreate, session: SessionDep, current_user: CurrentUser):
    current_user_id = current_user.id
    db_room = Room(
        room_name=room.room_name,
        max_players=room.max_players,
        number_of_actions=room.number_of_actions,
        created_by=current_user_id,
    )
    session.add(db_room)
    session.commit()
    session.refresh(db_room)
    print(db_room.id)
    return db_room


@router.get("/rooms")
async def get_rooms(session: SessionDep):
    rooms = session.exec(select(Room)).all()
    return rooms


@router.get("/room/{room_id}")
async def get_room(room_id: int, session: SessionDep):
    room = session.exec(select(Room).where(Room.id == room_id)).first()
    return room