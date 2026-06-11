from datetime import date, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Doctor, DoctorAvailability, DoctorSpecialization, Specialization, User
from app.utils.clinic_time import clinic_today, is_slot_past
from app.utils.doctor_avatar import resolve_doctor_profile_image_url

DEFAULT_SLOT_TIMES = [time(9, 0), time(11, 0), time(14, 0), time(16, 0), time(17, 30), time(18, 0), time(18, 30)]


def _doctor_payload(doctor: Doctor, user: User, specializations: list[str]) -> dict:
    summary = doctor.professional_summary or doctor.bio
    return {
        "id": doctor.id,
        "name": user.name,
        "experience_years": doctor.experience_years,
        "rating": float(doctor.rating),
        "specializations": specializations,
        "bio": doctor.bio,
        "qualifications": doctor.qualifications,
        "profile_image_url": resolve_doctor_profile_image_url(user.name, doctor.profile_image_url),
        "consultation_fee": float(doctor.consultation_fee) if doctor.consultation_fee is not None else None,
        "hospital_name": doctor.hospital_name,
        "clinic_address": doctor.clinic_address,
        "professional_summary": summary,
    }


def _format_time(t: time) -> str:
    h = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    return f"{h}:{t.minute:02d} {ampm}"


def _day_label(d: date) -> str:
    today = clinic_today()
    if d == today:
        return "Today"
    if d == today + timedelta(days=1):
        return "Tomorrow"
    return str(d)


def _filter_bookable_slots(slot_date: date, slot_time: time) -> bool:
    return not is_slot_past(slot_date, slot_time)


async def get_or_create_specialization(db: AsyncSession, name: str) -> Specialization:
    result = await db.execute(select(Specialization).where(Specialization.name == name))
    spec = result.scalar_one_or_none()
    if spec:
        return spec
    spec = Specialization(name=name, description=f"{name} specialist")
    db.add(spec)
    await db.flush()
    return spec


async def create_default_availability(
    db: AsyncSession, doctor_id: UUID, days: int = 14, slot_times: list[time] | None = None
) -> int:
    """Create default open slots for a new doctor (idempotent per slot)."""
    slot_times = slot_times or DEFAULT_SLOT_TIMES
    today = clinic_today()
    end = today + timedelta(days=max(days - 1, 0))
    existing_rows = await db.execute(
        select(DoctorAvailability.slot_date, DoctorAvailability.slot_time).where(
            DoctorAvailability.doctor_id == doctor_id,
            DoctorAvailability.slot_date >= today,
            DoctorAvailability.slot_date <= end,
        )
    )
    existing = {(row.slot_date, row.slot_time) for row in existing_rows.all()}

    added = 0
    for day_offset in range(days):
        d = today + timedelta(days=day_offset)
        for slot in slot_times:
            if (d, slot) in existing:
                continue
            db.add(DoctorAvailability(doctor_id=doctor_id, slot_date=d, slot_time=slot, status="available"))
            existing.add((d, slot))
            added += 1
    if added:
        await db.flush()
    return added


async def doctor_has_future_slots(db: AsyncSession, doctor_id: UUID) -> bool:
    today = clinic_today()
    row = await db.execute(
        select(DoctorAvailability.id)
        .where(DoctorAvailability.doctor_id == doctor_id, DoctorAvailability.slot_date >= today)
        .limit(1)
    )
    return row.scalar_one_or_none() is not None


async def list_doctors(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Doctor, User)
        .join(User, Doctor.user_id == User.id)
        .where(User.is_active.is_(True))
        .order_by(User.name)
    )
    doctors = []
    for doctor, user in result.all():
        specs = await db.execute(
            select(Specialization.name)
            .join(DoctorSpecialization, Specialization.id == DoctorSpecialization.specialization_id)
            .where(DoctorSpecialization.doctor_id == doctor.id)
        )
        doctors.append(_doctor_payload(doctor, user, [s[0] for s in specs.all()]))
    return doctors


async def _fetch_doctor_slots(
    db: AsyncSession, doctor_id: UUID, doctor_name: str, limit: int = 30
) -> list[dict]:
    today = clinic_today()
    rows = await db.execute(
        select(DoctorAvailability)
        .where(
            DoctorAvailability.doctor_id == doctor_id,
            DoctorAvailability.slot_date >= today,
            DoctorAvailability.status == "available",
        )
        .order_by(DoctorAvailability.slot_date, DoctorAvailability.slot_time)
        .limit(max(limit * 4, 40))
    )
    slots = []
    for s in rows.scalars().all():
        if not _filter_bookable_slots(s.slot_date, s.slot_time):
            continue
        slots.append({
            "doctor_id": str(doctor_id),
            "doctor_name": doctor_name,
            "slot_date": s.slot_date.isoformat(),
            "slot_time": s.slot_time.isoformat(),
            "label": f"{_day_label(s.slot_date)}: {_format_time(s.slot_time)}",
        })
        if len(slots) >= limit:
            break
    return slots


async def list_doctors_with_availability(
    db: AsyncSession,
    specialty: str | None = None,
    slots_per_doctor: int = 30,
    include_without_slots: bool = False,
) -> list[dict]:
    """All doctors from PostgreSQL with live availability slots."""
    all_docs = await list_doctors(db)
    result = []
    for doc in all_docs:
        slots = await _fetch_doctor_slots(db, doc["id"], doc["name"], limit=slots_per_doctor)
        if not slots and not include_without_slots:
            continue
        spec = doc["specializations"][0] if doc["specializations"] else "General Physician"
        entry = {
            "id": str(doc["id"]),
            "name": doc["name"],
            "specialty": spec,
            "specializations": doc["specializations"],
            "experience_years": doc["experience_years"],
            "rating": doc["rating"],
            "qualifications": doc.get("qualifications"),
            "profile_image_url": doc.get("profile_image_url"),
            "consultation_fee": doc.get("consultation_fee"),
            "hospital_name": doc.get("hospital_name"),
            "clinic_address": doc.get("clinic_address"),
            "professional_summary": doc.get("professional_summary"),
            "bio": doc.get("bio"),
            "slots": slots,
            "next_available": slots[0]["label"] if slots else "No slots open",
        }
        result.append(entry)

    if specialty:
        needle = specialty.lower()
        aliases = {
            "orthopedic": "orthopedic surgeon",
            "orthopedist": "orthopedic surgeon",
            "ent": "ent specialist",
        }
        needle = aliases.get(needle, needle)
        matched = [
            d for d in result
            if any(needle in s.lower() or s.lower() in needle for s in d["specializations"])
        ]
        result = matched if matched else result
    result.sort(key=lambda d: (-d["rating"], -d["experience_years"]))
    return result


async def get_recommended_doctors(db: AsyncSession, specialty: str) -> list[dict]:
    """Doctors with availability, specialty matches sorted first."""
    rows = await list_doctors_with_availability(db, specialty=specialty)
    for doc in rows:
        if doc["slots"]:
            doc["next_slot"] = f"{doc['slots'][0]['slot_date']} {doc['slots'][0]['slot_time']}"
    return rows


async def get_availability(db: AsyncSession, doctor_id: UUID, from_date: date | None = None) -> list[dict]:
    from_date = from_date or clinic_today()
    result = await db.execute(
        select(DoctorAvailability)
        .where(
            DoctorAvailability.doctor_id == doctor_id,
            DoctorAvailability.slot_date >= from_date,
            DoctorAvailability.status == "available",
        )
        .order_by(DoctorAvailability.slot_date, DoctorAvailability.slot_time)
    )
    return [
        {"date": str(s.slot_date), "time": str(s.slot_time), "status": s.status}
        for s in result.scalars().all()
        if _filter_bookable_slots(s.slot_date, s.slot_time)
    ]
