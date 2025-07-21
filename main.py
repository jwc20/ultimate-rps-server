from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated
from dataclasses import dataclass
from websocket import WebsocketManager
import bcrypt

import jwt
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, create_engine, select
from starlette.middleware.cors import CORSMiddleware
import httpx
from starlette.middleware import Middleware

SECRET_KEY = "d1476829cf5d3ea5326220b34a3d6ab78031d28f6b75d2575d9177f4e21a7fa4"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


# https://github.com/pyca/bcrypt/issues/684#issuecomment-2430047176
@dataclass
class SolveBugBcryptWarning:
    __version__: str = getattr(bcrypt, "__version__")


# Password hashing
setattr(bcrypt, "__about__", SolveBugBcryptWarning())
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# App initialization
@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield
    print("shutting down")


def add_cors_middleware(app):
    return CORSMiddleware(
        app=app,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )


def add_logging_middleware(app):
    async def middleware(scope, receive, send):
        path = scope["path"]
        print("Request:", path)
        await app(scope, receive, send)

    return middleware


app = FastAPI(lifespan=lifespan)
app.add_middleware(add_cors_middleware)


manager = WebsocketManager()

# Authentication Models
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


# User Models
class UserBase(SQLModel):
    username: str = Field(unique=True, index=True)
    disabled: bool = Field(default=False)


class User(UserBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    hashed_password: str


class UserCreate(BaseModel):
    username: str
    password: str


class UserPublic(BaseModel):
    id: int
    username: str
    disabled: bool


class UserUpdate(BaseModel):
    disabled: bool | None = None
    password: str | None = None

class RoomBase(SQLModel):
    room_name: str = Field(index=True)
    max_players: int = Field(default=None)
    number_of_actions: int = Field(default=None)

class Room(RoomBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

class RoomCreate(RoomBase):
    room_name: str 
    max_players: int | None = 2 
    number_of_actions: int | None = 3


# Database setup
sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"
connect_args = {"check_same_thread": False}
engine = create_engine(sqlite_url, connect_args=connect_args)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


# Authentication functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def get_user_by_username(session: Session, username: str):
    statement = select(User).where(User.username == username)
    user = session.exec(statement).first()
    return user


def authenticate_user(session: Session, username: str, password: str):
    user = get_user_by_username(session, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except InvalidTokenError:
        raise credentials_exception
    user = get_user_by_username(session, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


CurrentUser = Annotated[User, Depends(get_current_active_user)]


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


# Authentication endpoints
@app.post("/register", response_model=UserPublic)
def register(user: UserCreate, session: SessionDep):
    # Check if user already exists
    db_user = get_user_by_username(session, user.username)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Create new user
    hashed_password = get_password_hash(user.password)
    db_user = User(
        username=user.username,
        hashed_password=hashed_password,
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user

@app.post("/create-room")
async def create_room(room: RoomCreate, session: SessionDep):
    db_room = Room(
        room_name=room.room_name,
        max_players=room.max_players,
        number_of_actions=room.number_of_actions,
    )
    session.add(db_room)
    session.commit()
    session.refresh(db_room)
    return db_room

@app.get("/rooms")
async def get_rooms( session: SessionDep):
    rooms = session.exec(select(Room)).all()
    return rooms
    
    
    

@app.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
) -> Token:
    user = authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")
    

@app.get("/users/me/", response_model=UserPublic)
async def read_current_user(current_user: CurrentUser):
    return current_user


# User management endpoints (protected)
@app.post("/users/", response_model=UserPublic)
def create_user(user: UserCreate, session: SessionDep, current_user: CurrentUser):
    # Check if user already exists
    db_user = get_user_by_username(session, user.username)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists"
        )

    # Create new user
    hashed_password = get_password_hash(user.password)
    db_user = User(
        username=user.username,
        hashed_password=hashed_password,
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


@app.get("/users/", response_model=list[UserPublic])
def read_users(
    session: SessionDep,
    current_user: CurrentUser,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
):
    users = session.exec(select(User).offset(offset).limit(limit)).all()
    return users


@app.get("/users/{user_id}", response_model=UserPublic)
def read_user(user_id: int, session: SessionDep, current_user: CurrentUser):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.patch("/users/{user_id}", response_model=UserPublic)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    session: SessionDep,
    current_user: CurrentUser,
):
    user_db = session.get(User, user_id)
    if not user_db:
        raise HTTPException(status_code=404, detail="User not found")

    # Handle password update separately
    user_data = user_update.model_dump(exclude_unset=True, exclude={"password"})

    # Update password if provided
    if user_update.password is not None:
        user_data["hashed_password"] = get_password_hash(user_update.password)

    # Update user fields
    user_db.sqlmodel_update(user_data)
    session.add(user_db)
    session.commit()
    session.refresh(user_db)
    return user_db


@app.delete("/users/{user_id}")
def delete_user(user_id: int, session: SessionDep, current_user: CurrentUser):
    # Prevent users from deleting themselves
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    session.delete(user)
    session.commit()
    return {"ok": True}


@app.get("/")
def root():
    return {"hello": "world"}
