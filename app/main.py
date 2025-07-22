from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database import create_db_and_tables
from app.middleware import add_cors_middleware
from app.routers import auth_router, users_router, rooms_router, websocket_router

from broadcaster import Broadcast
from app.routers.websocket import init_room_manager


broadcast = Broadcast("redis://localhost:6379")


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    await broadcast.connect()
    await init_room_manager(broadcast)
    yield
    await broadcast.disconnect()
    print("shutting down")


app = FastAPI(lifespan=lifespan)
app.add_middleware(add_cors_middleware)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(rooms_router)
app.include_router(websocket_router)
