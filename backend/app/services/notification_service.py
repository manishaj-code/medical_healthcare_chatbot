"""In-app notifications — list, unread count, mark read."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system import Notification


def _serialize(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "type": n.type.value if hasattr(n.type, "value") else str(n.type),
        "message": n.message,
        "sent_at": n.sent_at.isoformat() if n.sent_at else None,
        "read_at": n.read_at.isoformat() if n.read_at else None,
        "is_read": n.read_at is not None,
    }


async def list_notifications_for_user(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 30,
) -> list[dict]:
    rows = await db.execute(
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.sent_at.desc())
        .limit(limit)
    )
    return [_serialize(n) for n in rows.scalars().all()]


async def count_unread_notifications(db: AsyncSession, user_id: UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
    )
    return int(result.scalar() or 0)


async def mark_notifications_read(
    db: AsyncSession,
    user_id: UUID,
    notification_ids: list[UUID] | None = None,
) -> int:
    now = datetime.now(timezone.utc)
    stmt = (
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=now)
    )
    if notification_ids:
        stmt = stmt.where(Notification.id.in_(notification_ids))
    result = await db.execute(stmt)
    await db.flush()
    return int(result.rowcount or 0)
