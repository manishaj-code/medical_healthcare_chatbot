from datetime import date, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Doctor, DoctorAvailability, DoctorSpecialization, Specialization, User

DEFAULT_SLOT_TIMES = [time(9, 0), time(11, 0), time(14, 0), time(16, 0), time(17, 30), time(18, 0), time(18, 30)]


def _format_time(t: time) -> str:
    h = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    return f"{h}:{t.minute:02d} {ampm}"


def _day_label(d: date) -> str:
    today = date.today()
    if d == today:
        return "Today"
    if d == today + timedelta(days=1):
        return "Tomorrow"
    return str(d)


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
    today = date.today()
    added = 0
    for day_offset in range(days):
        d = today + timedelta(days=day_offset)
        for slot in slot_times:
            exists = await db.execute(
                select(DoctorAvailability).where(
                    DoctorAvailability.doctor_id == doctor_id,
                    DoctorAvailability.slot_date == d,
                    DoctorAvailability.slot_time == slot,
                )
            )
            if not exists.scalar_one_or_none():
                db.add(DoctorAvailability(doctor_id=doctor_id, slot_date=d, slot_time=slot, status="available"))
                added += 1
    await db.flush()
    return added


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
        doctors.append({
            "id": doctor.id,
            "name": user.name,
            "experience_years": doctor.experience_years,
            "rating": float(doctor.rating),
            "specializations": [s[0] for s in specs.all()],
            "bio": doctor.bio,
        })
    return doctors


async def _fetch_doctor_slots(
    db: AsyncSession, doctor_id: UUID, doctor_name: str, limit: int = 6
) -> list[dict]:
    today = date.today()
    rows = await db.execute(
        select(DoctorAvailability)
        .where(
            DoctorAvailability.doctor_id == doctor_id,
            DoctorAvailability.slot_date >= today,
            DoctorAvailability.status == "available",
        )
        .order_by(DoctorAvailability.slot_date, DoctorAvailability.slot_time)
        .limit(limit)
    )
    slots = []
    for s in rows.scalars().all():
        slots.append({
            "doctor_id": str(doctor_id),
            "doctor_name": doctor_name,
            "slot_date": s.slot_date.isoformat(),
            "slot_time": s.slot_time.isoformat(),
            "label": f"{_day_label(s.slot_date)}: {_format_time(s.slot_time)}",
        })
    return slots


async def list_doctors_with_availability(
    db: AsyncSession,
    specialty: str | None = None,
    slots_per_doctor: int = 6,
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
            "slots": slots,
            "next_available": slots[0]["label"] if slots else "No slots open",
        }
        result.append(entry)

    if specialty:
        matched = [
            d for d in result
            if any(specialty.lower() == s.lower() for s in d["specializations"])
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
    from_date = from_date or date.today()
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
    ]
