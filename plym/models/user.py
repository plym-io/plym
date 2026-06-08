from pydantic import BaseModel, Field

from plym.models.common import ORMModel, Role, Timestamped
from plym.models.email import PlymEmail


class UserCreate(BaseModel):
    email: PlymEmail
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=120)
    role: Role = Role.READER


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    bio: str | None = None
    avatar_url: str | None = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)


class AdminPasswordReset(BaseModel):
    new_password: str = Field(min_length=8)


class User(Timestamped):
    id: int
    email: PlymEmail
    role: Role
    is_active: bool
    display_name: str
    bio: str | None = None
    avatar_url: str | None = None


class UserPublic(ORMModel):
    id: int
    display_name: str
    avatar_url: str | None = None
