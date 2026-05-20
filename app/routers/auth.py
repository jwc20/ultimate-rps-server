from datetime import timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.database import SessionDep
from app.schemas import Token, UserCreate, UserPublic
from app.auth import authenticate_user, create_access_token, get_password_hash
from app.auth.utils import get_user_by_username
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter()


@router.post("/register", response_model=UserPublic)
def register(user: UserCreate, conn: SessionDep):
    db_user = get_user_by_username(conn, user.username)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    hashed_password = get_password_hash(user.password)
    username_clean = user.username.lower().strip()
    cursor = conn.execute(
        "INSERT INTO user (username, hashed_password) VALUES (?, ?)",
        (username_clean, hashed_password),
    )
    user_id = cursor.lastrowid
    return UserPublic(id=user_id, username=username_clean, disabled=False)


@router.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], conn: SessionDep
) -> Token:
    user = authenticate_user(conn, form_data.username, form_data.password)
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