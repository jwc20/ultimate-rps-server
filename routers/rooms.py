from fastapi import APIRouter
from sqlmodel import select
from database import SessionDep
from models import Room
from schemas import RoomCreate

router = APIRouter()


@router.post("/create-room")
async def create_room(room: RoomCreate, session: SessionDep):
    db_room = Room(
        room_name=room.room_name,
        max_players=room.max_players,
        number_of_actions=room.number_of_actions,
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