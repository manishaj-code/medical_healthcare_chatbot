from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_current_user
from app.database import get_db
from app.models import Specialization
from app.schemas.common import ResponseEnvelope
from app.services.doctor_service import get_availability, get_recommended_doctors, list_doctors, list_doctors_with_availability

router = APIRouter(prefix="/doctors", tags=["doctors"])


@router.get("/specializations")
async def specializations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Specialization))
    return ResponseEnvelope(data=[{"id": str(s.id), "name": s.name} for s in result.scalars().all()])


@router.get("")
async def doctors_list(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    return ResponseEnvelope(data=await list_doctors(db))


@router.get("/with-availability")
async def doctors_with_availability(
    specialty: str | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """All doctors from DB with open slots — used by patient UI and chatbot."""
    return ResponseEnvelope(data=await list_doctors_with_availability(db, specialty=specialty))


@router.get("/recommended")
async def recommended(
    specialty: str = Query(default="General Physician"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return ResponseEnvelope(data=await get_recommended_doctors(db, specialty))


@router.get("/{doctor_id}/availability")
async def availability(
    doctor_id: UUID,
    from_date: date | None = None,
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    return ResponseEnvelope(data=await get_availability(db, doctor_id, from_date))
