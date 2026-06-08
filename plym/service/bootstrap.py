from plym.db.session import get_session_factory
from plym.models.common import Role
from plym.repository.user_repository import UserRepository
from plym.service.password_service import PasswordService
from plym.settings import settings


async def ensure_superuser() -> None:
    factory = get_session_factory()
    async with factory() as session:
        users = UserRepository(session)
        if await users.exists_by_email(settings.superuser_email):
            return
        passwords = PasswordService()
        await users.create(
            email=settings.superuser_email,
            password_hash=passwords.hash(settings.superuser_password),
            role=Role.ADMINISTRATOR.value,
            display_name="Administrator",
        )
        await session.commit()
