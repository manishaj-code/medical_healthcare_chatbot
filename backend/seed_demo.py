"""Ensure demo slots and data exist on every startup (safe to re-run)."""
import asyncio
from datetime import date, time, timedelta

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Doctor, DoctorAvailability, Medication, Patient, User

JOHN_DEMO_MEDICATIONS = (
    ("Metformin", "500mg", "twice daily"),
    ("Amlodipine", "5mg", "once daily"),
    ("Atorvastatin", "10mg", "once at night"),
)

EXTRA_EVENING_SLOTS = [time(17, 30), time(18, 0), time(18, 30)]


async def ensure_john_medications(db, patient: Patient) -> int:
    rows = await db.execute(select(Medication).where(Medication.patient_id == patient.id))
    existing = {m.name.lower() for m in rows.scalars().all()}
    added = 0
    for name, dosage, frequency in JOHN_DEMO_MEDICATIONS:
        if name.lower() in existing:
            continue
        db.add(
            Medication(
                patient_id=patient.id,
                name=name,
                dosage=dosage,
                frequency=frequency,
                is_active=True,
            )
        )
        added += 1
    return added


async def ensure_demo_data() -> None:
    async with AsyncSessionLocal() as db:
        patient_row = await db.execute(select(Patient).join(User).where(User.email == "john@test.com"))
        patient = patient_row.scalar_one_or_none()
        if not patient:
            return

        med_added = await ensure_john_medications(db, patient)

        doctors = (await db.execute(select(Doctor))).scalars().all()
        if not doctors:
            if med_added:
                await db.commit()
                print(f"Demo data: added {med_added} medication(s) for john@test.com.")
            return

        doctor_ids = [doc.id for doc in doctors]
        today = date.today()
        end = today + timedelta(days=6)
        existing_rows = await db.execute(
            select(
                DoctorAvailability.doctor_id,
                DoctorAvailability.slot_date,
                DoctorAvailability.slot_time,
            ).where(
                DoctorAvailability.doctor_id.in_(doctor_ids),
                DoctorAvailability.slot_date >= today,
                DoctorAvailability.slot_date <= end,
                DoctorAvailability.slot_time.in_(EXTRA_EVENING_SLOTS),
            )
        )
        existing = {
            (row.doctor_id, row.slot_date, row.slot_time) for row in existing_rows.all()
        }

        added = 0
        for doc in doctors:
            for day_offset in range(7):
                d = today + timedelta(days=day_offset)
                for slot in EXTRA_EVENING_SLOTS:
                    key = (doc.id, d, slot)
                    if key in existing:
                        continue
                    db.add(
                        DoctorAvailability(
                            doctor_id=doc.id,
                            slot_date=d,
                            slot_time=slot,
                            status="available",
                        )
                    )
                    existing.add(key)
                    added += 1

        if added or med_added:
            await db.commit()
            if med_added:
                print(f"Demo data: added {med_added} medication(s) for john@test.com.")
            if added:
                print(f"Demo data: added {added} evening slots.")


if __name__ == "__main__":
    asyncio.run(ensure_demo_data())
