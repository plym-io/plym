import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from plym.settings import settings


class TokenService:
    algorithm = "HS256"

    def issue_access(self, user_id: int, role: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "role": role,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=settings.jwt_access_ttl_seconds)).timestamp()),
            "typ": "access",
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=self.algorithm)

    def decode_access(self, token: str) -> dict:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[self.algorithm],
            options={"require": ["exp", "sub", "typ"]},
        )

    def generate_refresh(self) -> tuple[str, str, datetime]:
        raw = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=settings.jwt_refresh_ttl_seconds
        )
        return raw, token_hash, expires_at

    def hash_refresh(self, raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
