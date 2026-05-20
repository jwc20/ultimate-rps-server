from dataclasses import dataclass, field


@dataclass
class User:
    username: str
    hashed_password: str
    is_admin: bool = False
    disabled: bool = False
    id: int | None = None
