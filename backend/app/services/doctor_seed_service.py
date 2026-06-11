"""Seed and upsert the MediAI doctor catalog."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.doctors_catalog import (
    DOCTOR_CATALOG,
    DOCTOR_DEFAULT_PASSWORD,
    SPECIALTIES,
    DoctorSeed,
)
from app.database import hash_password
from app.models import Doctor, DoctorSpecialization, User
from app.models.enums import UserRole
from app.services.doctor_service import (
    create_default_availability,
    doctor_has_future_slots,
    get_or_create_specialization,
)
from app.utils.doctor_avatar import is_legacy_cartoon_avatar


def _field_changed(current, new) -> bool:
    if current is None and new is None:
        return False
    try:
        return float(current) != float(new)
    except (TypeError, ValueError):
        return current != new


def _doctor_fields(record: DoctorSeed) -> dict:
    return {
        "experience_years": record.experience_years,
        "rating": record.rating,
        "bio": record.professional_summary,
        "professional_summary": record.professional_summary,
        "qualifications": record.qualifications,
        "profile_image_url": record.profile_image_url,
        "consultation_fee": record.consultation_fee,
        "hospital_name": record.hospital_name,
        "clinic_address": record.clinic_address,
        "is_verified": True,
    }


async def _link_specialty(db: AsyncSession, doctor_id, spec_map: dict, specialty: str) -> None:
    spec = spec_map[specialty]
    exists = await db.execute(
        select(DoctorSpecialization).where(
            DoctorSpecialization.doctor_id == doctor_id,
            DoctorSpecialization.specialization_id == spec.id,
        )
    )
    if not exists.scalar_one_or_none():
        db.add(DoctorSpecialization(doctor_id=doctor_id, specialization_id=spec.id))


async def _prune_doctors_not_in_catalog(db: AsyncSession) -> int:
    """Remove doctor accounts that are no longer in DOCTOR_CATALOG."""
    from app.services.admin_service import delete_doctor_account

    catalog_emails = {record.email.lower() for record in DOCTOR_CATALOG}
    rows = await db.execute(
        select(Doctor, User).join(User, User.id == Doctor.user_id).where(User.role == UserRole.doctor.value)
    )
    removed = 0
    for doctor, user in rows.all():
        if user.email.lower() not in catalog_emails:
            await delete_doctor_account(db, doctor.id)
            removed += 1
    return removed


async def seed_doctor_catalog(db: AsyncSession) -> tuple[int, int, int]:
    """Insert missing doctors, refresh profiles, and drop catalog extras."""
    spec_map: dict[str, object] = {}
    for name in SPECIALTIES:
        spec_map[name] = await get_or_create_specialization(db, name)
    await db.flush()

    added = 0
    updated = 0
    for record in DOCTOR_CATALOG:
        user_row = await db.execute(select(User).where(User.email == record.email))
        user = user_row.scalar_one_or_none()

        if user:
            doc_row = await db.execute(select(Doctor).where(Doctor.user_id == user.id))
            doctor = doc_row.scalar_one_or_none()
            if doctor:
                changed = False
                for key, value in _doctor_fields(record).items():
                    current = getattr(doctor, key)
                    if _field_changed(current, value) or (
                        key == "profile_image_url" and is_legacy_cartoon_avatar(current)
                    ):
                        setattr(doctor, key, value)
                        changed = True
                if user.name != record.name:
                    user.name = record.name
                    changed = True
                await _link_specialty(db, doctor.id, spec_map, record.specialty)
                if not await doctor_has_future_slots(db, doctor.id):
                    if await create_default_availability(db, doctor.id):
                        changed = True
                if changed:
                    updated += 1
            continue

        user = User(
            name=record.name,
            email=record.email,
            password_hash=hash_password(DOCTOR_DEFAULT_PASSWORD),
            role=UserRole.doctor.value,
        )
        db.add(user)
        await db.flush()

        doctor = Doctor(user_id=user.id, **_doctor_fields(record))
        db.add(doctor)
        await db.flush()
        await _link_specialty(db, doctor.id, spec_map, record.specialty)
        await create_default_availability(db, doctor.id)
        added += 1

    removed = await _prune_doctors_not_in_catalog(db)
    await db.flush()
    return added, updated, removed
