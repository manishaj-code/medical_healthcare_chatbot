"""Map guest session IDs to stable flow-state conversation IDs (shared with patient chat)."""
from __future__ import annotations

import uuid

GUEST_FLOW_NAMESPACE = uuid.UUID("a3b8c9d0-1111-4f5e-9a2b-3c4d5e6f7890")


def guest_flow_conversation_id(session_id: str) -> uuid.UUID:
    return uuid.uuid5(GUEST_FLOW_NAMESPACE, session_id)
