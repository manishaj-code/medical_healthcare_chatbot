from uuid import UUID

from pydantic import BaseModel, Field


class NotificationUnreadCountResponse(BaseModel):
    count: int


class MarkNotificationsReadRequest(BaseModel):
    ids: list[UUID] | None = Field(
        default=None,
        description="Notification IDs to mark read; omit to mark all unread",
    )


class MarkNotificationsReadResponse(BaseModel):
    marked: int
