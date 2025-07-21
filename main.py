from contextlib import asynccontextmanager
from fastapi import FastAPI
from database import create_db_and_tables
from middleware import add_cors_middleware
from routers import auth_router, users_router, rooms_router, websocket_router
from routers.websocket import broadcast

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    await broadcast.connect()
    yield
    await broadcast.disconnect()
    print("shutting down")


app = FastAPI(lifespan=lifespan)
app.add_middleware(add_cors_middleware)

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(rooms_router)
app.include_router(websocket_router)


@app.get("/")
def root():
    return {"hello": "world"}