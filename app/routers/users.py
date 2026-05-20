from typing import Annotated
from fastapi import APIRouter, HTTPException, Query, status
from app.database import SessionDep
from app.schemas import UserCreate, UserPublic, UserUpdate, UserUpdatePassword, UserUpdateUsername, UserUpdateResponse, AdminResetPassword
from app.auth import CurrentUser, get_password_hash
from app.auth.utils import get_user_by_username, verify_password

router = APIRouter(prefix="/users", tags=["users"])

# Whitelists guard against column-name injection when building dynamic UPDATE clauses
_ALLOWED_USER_UPDATE_COLS = {"username", "disabled", "hashed_password"}
_ALLOWED_USERNAME_UPDATE_COLS = {"username"}


def _row_to_user_public(row) -> UserPublic:
    return UserPublic(id=row["id"], username=row["username"], disabled=bool(row["disabled"]))


@router.get("/me/", response_model=UserPublic)
async def read_current_user(current_user: CurrentUser):
    return UserPublic(id=current_user.id, username=current_user.username, disabled=current_user.disabled)


@router.post("/", response_model=UserPublic)
def create_user(user: UserCreate, conn: SessionDep, current_user: CurrentUser):
    db_user = get_user_by_username(conn, user.username)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists"
        )

    hashed_password = get_password_hash(user.password)
    username_clean = user.username.lower().strip()
    cursor = conn.execute(
        "INSERT INTO user (username, hashed_password) VALUES (?, ?)",
        (username_clean, hashed_password),
    )
    user_id = cursor.lastrowid
    return UserPublic(id=user_id, username=username_clean, disabled=False)


@router.get("/", response_model=list[UserPublic])
def read_users(
        conn: SessionDep,
        current_user: CurrentUser,
        offset: int = 0,
        limit: Annotated[int, Query(le=100)] = 100,
):
    cursor = conn.execute(
        "SELECT id, username, disabled FROM user LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return [_row_to_user_public(row) for row in cursor.fetchall()]


@router.get("/{user_id}", response_model=UserPublic)
def read_user(user_id: int, conn: SessionDep, current_user: CurrentUser):
    cursor = conn.execute(
        "SELECT id, username, disabled FROM user WHERE id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return _row_to_user_public(row)


@router.patch("/{user_id}", response_model=UserPublic)
def update_user(
        user_id: int,
        user_update: UserUpdate,
        conn: SessionDep,
        current_user: CurrentUser,
):
    cursor = conn.execute(
        "SELECT id, username, disabled FROM user WHERE id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    updates = user_update.model_dump(exclude_unset=True, exclude={"password"})
    if user_update.password is not None:
        updates["hashed_password"] = get_password_hash(user_update.password)

    updates = {k: v for k, v in updates.items() if k in _ALLOWED_USER_UPDATE_COLS}
    if updates:
        set_clause = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [user_id]
        conn.execute(f"UPDATE user SET {set_clause} WHERE id = ?", values)

    cursor = conn.execute(
        "SELECT id, username, disabled FROM user WHERE id = ?",
        (user_id,),
    )
    return _row_to_user_public(cursor.fetchone())


@router.delete("/{user_id}")
def delete_user(user_id: int, conn: SessionDep, current_user: CurrentUser):
    if current_user.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    cursor = conn.execute("SELECT id FROM user WHERE id = ?", (user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="User not found")

    conn.execute("DELETE FROM user WHERE id = ?", (user_id,))
    return {"ok": True}


@router.patch("/{user_id}/change-username")
def change_user_username(user_id: int, user_update_username: UserUpdateUsername, conn: SessionDep,
                         current_user: CurrentUser):
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only change your own password"
        )
    cursor = conn.execute("SELECT id FROM user WHERE id = ?", (user_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="User not found")

    updates = user_update_username.model_dump(exclude_unset=True)
    updates = {k: v for k, v in updates.items() if k in _ALLOWED_USERNAME_UPDATE_COLS}
    if updates:
        set_clause = ", ".join(f"{key} = ?" for key in updates)
        values = list(updates.values()) + [user_id]
        conn.execute(f"UPDATE user SET {set_clause} WHERE id = ?", values)

    cursor = conn.execute(
        "SELECT id, username, disabled FROM user WHERE id = ?",
        (user_id,),
    )
    return _row_to_user_public(cursor.fetchone())


@router.patch("/{user_id}/change-password")
def change_user_password(
        user_id: int,
        user_update_password: UserUpdatePassword,
        conn: SessionDep,
        current_user: CurrentUser
) -> UserUpdateResponse:
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only change your own password"
        )
    cursor = conn.execute(
        "SELECT id, hashed_password FROM user WHERE id = ?",
        (user_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not verify_password(user_update_password.current_password, row["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )

    if verify_password(user_update_password.new_password, row["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password"
        )

    new_hash = get_password_hash(user_update_password.new_password)
    conn.execute(
        "UPDATE user SET hashed_password = ? WHERE id = ?",
        (new_hash, user_id),
    )
    return UserUpdateResponse(
        message="Password changed successfully",
        user_id=user_id
    )


# @router.patch("/{user_id}/reset-password")
# def admin_reset_user_password(
#         user_id: int,
#         new_password: AdminResetPassword,
#         conn: SessionDep,
#         current_user: CurrentUser
# ):
#     if not current_user.is_admin:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Admin access required"
#         )
#
#     cursor = conn.execute("SELECT id FROM user WHERE id = ?", (user_id,))
#     if not cursor.fetchone():
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="User not found"
#         )
#
#     new_hash = get_password_hash(new_password.new_password)
#     conn.execute(
#         "UPDATE user SET hashed_password = ? WHERE id = ?",
#         (new_hash, user_id),
#     )
#     return {"message": f"Password reset for user {user_id}", "user_id": user_id}
