import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from passlib.context import CryptContext
from app.models import User
from app.config import SECRET_KEY, ALGORITHM


@dataclass
class SolveBugBcryptWarning:
    __version__: str = getattr(bcrypt, "__version__")


setattr(bcrypt, "__about__", SolveBugBcryptWarning())
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def get_user_by_username(conn: sqlite3.Connection, username: str) -> User | None:
    username_cleaned = username.lower().strip()
    cursor = conn.execute(
        "SELECT id, username, hashed_password, is_admin, disabled FROM user WHERE username = ?",
        (username_cleaned,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return User(
        id=row["id"],
        username=row["username"],
        hashed_password=row["hashed_password"],
        is_admin=bool(row["is_admin"]),
        disabled=bool(row["disabled"]),
    )


def authenticate_user(conn: sqlite3.Connection, username: str, password: str):
    user = get_user_by_username(conn, username)
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
        expire = datetime.now(timezone.utc) + timedelta(days=3)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt