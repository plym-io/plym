from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


class PasswordService:
    def hash(self, password: str) -> str:
        return _hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return _hasher.verify(password_hash, password)
        except VerifyMismatchError:
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        return _hasher.check_needs_rehash(password_hash)
