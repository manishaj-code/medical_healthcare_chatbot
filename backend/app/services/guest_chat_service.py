"""Guest landing chat — delegates to shared chat orchestrator."""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat_orchestrator import load_guest_chat_history, process_guest_message

__all__ = ["process_guest_message", "load_guest_chat_history"]
