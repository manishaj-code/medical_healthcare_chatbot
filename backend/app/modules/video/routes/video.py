from fastapi import APIRouter, Depends, HTTPException, status, Path
from livekit.api import AccessToken, VideoGrants
import os
import json
from app.database import get_current_user, get_db
from app.models import User
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

router = APIRouter(prefix="/video", tags=["video"])

LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

if not all([LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET]):
    # In production, you might want to raise an error or handle differently.
    # For now, we'll allow the router to be loaded but endpoints will error.
    pass

@router.post("/rooms/{room_id}/token")
async def get_token(
    room_id: str = Path(..., description="LiveKit room identifier"),
    # Expect same payload as VideoDemoPage
    participant_id: str = None,
    role: str = None,
    ttl: int = 3600,
    metadata: dict = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a LiveKit token for the given room and participant.
    The participant_id defaults to the current user's ID if not provided.
    Role defaults to 'guest' if not provided.
    """
    # Use authenticated user's ID if participant_id not supplied
    if participant_id is None:
        participant_id = str(user.id)
    if role is None:
        role = "guest"

    # Optional: validate that the user is allowed to join this room.
    # For simplicity, we allow any authenticated user to join any room.
    # In a real app, you would check appointments, etc.

    # Create video grant
    video_grants = VideoGrants(
        room_join=True,
        room=room_id,
        can_publish=True,
        can_subscribe=True,
        # Optional: add other permissions like can_publish_data, etc.
    )

    # Create access token
    token = AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    token.with_identity(participant_id)
    token.with_name(metadata.get("displayName") if metadata and "displayName" in metadata else participant_id)
    token.with_grants(video_grants)
    token.with_ttl(ttl)
    # Optionally add metadata as JSON string
    if metadata:
        token.with_metadata(json.dumps(metadata))
    jwt_token = token.to_jwt()

    return {
        "token": jwt_token,
        "url": LIVEKIT_URL,
    }

# Include this router in the main api_router
def init_video_router(main_router: APIRouter):
    main_router.include_router(router, prefix="/api/v1/video")