from typing import Annotated
from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import select
from database import SessionDep
from models import User
from schemas import UserCreate, UserPublic, UserUpdate
from auth import CurrentUser, get_password_hash
from auth.utils import get_user_by_username

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/", response_model=UserPublic)
async def read_current_user(current_user: CurrentUser):
    return current_user


@router.post("/", response_model=UserPublic)
def create_user(user: UserCreate, session: SessionDep, current_user: CurrentUser):
    db_user = get_user_by_username(session, user.username)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists"
        )

    hashed_password = get_password_hash(user.password)
    db_user = User(
        username=user.username,
        hashed_password=hashed_password,
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


@router.get("/", response_model=list[UserPublic])
def read_users(
    session: SessionDep,
    current_user: CurrentUser,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
):
    users = session.exec(select(User).offset(offset).limit(limit)).all()
    return users


@router.get("/{user_id}", response_model=UserPublic)
def read_user(user_id: int, session: SessionDep, current_user: CurrentUser):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserPublic)
def update_user(
    user_id: int,
    user_update: UserUpdate,
    session: SessionDep,
    current_user: CurrentUser,
):
    user_db = session.get(User, user_id)
    if not user_db:
        raise HTTPException(status_code=404, detail="User not found")

    user_data = user_update.model_dump(exclude_unset=True, exclude={"password"})

    if user_update.password is not None:
        user_data["hashed_password"] = get_password_hash(user_update.password)

    user_db.sqlmodel_update(user_data)
    session.add(user_db)
    session.commit()
    session.refresh(user_db)
    return user_db


@router.delete("/{user_id}")
def delete_user(user_id: int, session: SessionDep, current_user: CurrentUser):
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