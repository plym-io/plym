from pydantic import BaseModel

from plym.models.email import PlymEmail


class LoginRequest(BaseModel):
    email: PlymEmail
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
