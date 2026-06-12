"""Default platform accounts created on startup when missing."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import hash_password
from app.models import User
from app.models.enums import UserRole

DEFAULT_ADMIN_EMAIL = "admin@clinic.com"
DEFAULT_ADMIN_PASSWORD = "Admin@12345"
DEFAULT_ADMIN_NAME = "System Admin"


async def ensure_admin_account(db: AsyncSession) -> bool:
    """Ensure the default admin account exists and is active. Returns True if created."""
    result = await db.execute(select(User).where(User.email == DEFAULT_ADMIN_EMAIL))
    user = result.scalar_one_or_none()
    if user:
        changed = False
        if user.role != UserRole.admin.value:
            user.role = UserRole.admin.value
            changed = True
        if not user.is_active:
            user.is_active = True
            changed = True
        if changed:
            await db.flush()
        return False

    db.add(
        User(
            name=DEFAULT_ADMIN_NAME,
            email=DEFAULT_ADMIN_EMAIL,
            password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
            role=UserRole.admin.value,
            is_active=True,
        )
    )
    await db.flush()
    return True
