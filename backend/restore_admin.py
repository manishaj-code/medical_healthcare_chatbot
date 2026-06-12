"""Restore default admin login. Run from backend/: python restore_admin.py"""
import asyncio

from sqlalchemy import select

from app.database import AsyncSessionLocal, hash_password
from app.models import User
from app.models.enums import UserRole
from app.services.bootstrap_service import (
    DEFAULT_ADMIN_EMAIL,
    DEFAULT_ADMIN_NAME,
    DEFAULT_ADMIN_PASSWORD,
    ensure_admin_account,
)


async def restore() -> None:
    async with AsyncSessionLocal() as db:
        created = await ensure_admin_account(db)
        if not created:
            result = await db.execute(select(User).where(User.email == DEFAULT_ADMIN_EMAIL))
            user = result.scalar_one()
            user.name = DEFAULT_ADMIN_NAME
            user.password_hash = hash_password(DEFAULT_ADMIN_PASSWORD)
            user.role = UserRole.admin.value
            user.is_active = True
        await db.commit()
        print(f"Admin credentials ready: {DEFAULT_ADMIN_EMAIL} / {DEFAULT_ADMIN_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(restore())
