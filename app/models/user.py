from sqlmodel import Field, SQLModel


class UserBase(SQLModel):
    username: str = Field(unique=True, index=True)
    disabled: bool = Field(default=False)


class User(UserBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    hashed_password: str
    
    
# class UserGameState(SQLModel, table=True):
#     id: int | None = Field(default=None, primary_key=True)
#     user_id: int = Field(foreign_key="user.id", index=True)
#     wins: int = Field(default=0)
#     losses: int = Field(default=0)


