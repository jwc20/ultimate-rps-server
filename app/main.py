from fastapi import FastAPI
from app.core.middleware import setup_middleware
from app.routers import players, rooms, websocket

app = FastAPI(title="Rock Paper Scissors Game API")

# Setup middleware
setup_middleware(app)

# Include routers
app.include_router(players.router, prefix="/api", tags=["players"])
app.include_router(rooms.router, prefix="/api", tags=["rooms"])
app.include_router(websocket.router, tags=["websocket"])

@app.get("/")
async def root():
    return {"message": "Rock Paper Scissors Game API"}