"""Ensure demo slots and data exist on every startup (safe to re-run)."""
import asyncio
from datetime import date, time, timedelta

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import Doctor, DoctorAvailability, Patient, User


async def ensure_demo_data() -> None:
    async with AsyncSessionLocal() as db:
        patient_row = await db.execute(select(Patient).join(User).where(User.email == "john@test.com"))
        patient = patient_row.scalar_one_or_none()
        if not patient:
            return

        doctors = (await db.execute(select(Doctor))).scalars().all()
        extra_slots = [time(17, 30), time(18, 0), time(18, 30)]
        today = date.today()
        added = 0
        for doc in doctors:
            for day_offset in range(7):
                d = today + timedelta(days=day_offset)
                for slot in extra_slots:
                    exists = await db.execute(
                        select(DoctorAvailability).where(
                            DoctorAvailability.doctor_id == doc.id,
                            DoctorAvailability.slot_date == d,
                            DoctorAvailability.slot_time == slot,
                        )
                    )
                    if not exists.scalar_one_or_none():
                        db.add(
                            DoctorAvailability(
                                doctor_id=doc.id, slot_date=d, slot_time=slot, status="available"
                            )
                        )
                        added += 1
        if added:
            await db.commit()
            print(f"Demo data: added {added} evening slots.")


if __name__ == "__main__":
    asyncio.run(ensure_demo_data())
