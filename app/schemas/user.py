from pydantic import BaseModel


class UserCreate(BaseModel):
    username: str
    password: str


class UserPublic(BaseModel):
    id: int
    username: str
    disabled: bool


class UserUpdate(BaseModel):
    disabled: bool | None = None
    username: str | None = None
    password: str | None = None

class UserUpdatePassword(BaseModel):
    current_password: str | None = None
    new_password: str | None = None

class UserUpdateUsername(BaseModel):
    username: str | None = None

class UserUpdateResponse(BaseModel):
    message: str
    user_id: int
    
    
class AdminResetPassword(BaseModel):
    new_password: str