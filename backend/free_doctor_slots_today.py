"""Free all of today's slots for a doctor by name. Run: python free_doctor_slots_today.py "Sharma" """
import asyncio
import sys

from sqlalchemy import delete, select, update

from app.database import AsyncSessionLocal
from app.models import Appointment, AppointmentReminder, Doctor, DoctorAvailability, DoctorNote, PatientSummary, User
from app.models.enums import AppointmentStatus
from app.services.doctor_service import create_default_availability
from app.utils.clinic_time import clinic_today


async def free_today_slots(name_query: str) -> None:
    today = clinic_today()
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Doctor, User)
                .join(User, Doctor.user_id == User.id)
                .where(User.name.ilike(f"%{name_query}%"))
                .order_by(User.name)
            )
        ).all()
        if not rows:
            print(f"No doctor found matching '{name_query}'.")
            return
        if len(rows) > 1:
            print("Multiple matches:")
            for doctor, user in rows:
                print(f"  - {user.name} ({user.email}) id={doctor.id}")
            print("Use a more specific name query.")
            return

        doctor, user = rows[0]
        doctor_id = doctor.id
        print(f"Doctor: {user.name} ({user.email})")
        print(f"Date: {today.isoformat()}")

        appts = (
            await db.execute(
                select(Appointment).where(
                    Appointment.doctor_id == doctor_id,
                    Appointment.slot_date == today,
                )
            )
        ).scalars().all()

        if appts:
            appt_ids = [a.id for a in appts]
            await db.execute(delete(AppointmentReminder).where(AppointmentReminder.appointment_id.in_(appt_ids)))
            await db.execute(
                update(PatientSummary)
                .where(PatientSummary.appointment_id.in_(appt_ids))
                .values(appointment_id=None)
            )
            await db.execute(
                update(DoctorNote).where(DoctorNote.appointment_id.in_(appt_ids)).values(appointment_id=None)
            )
            await db.execute(
                delete(Appointment).where(
                    Appointment.doctor_id == doctor_id,
                    Appointment.slot_date == today,
                )
            )
            print(f"Removed {len(appts)} appointment(s) for today.")

        result = await db.execute(
            update(DoctorAvailability)
            .where(
                DoctorAvailability.doctor_id == doctor_id,
                DoctorAvailability.slot_date == today,
            )
            .values(status="available")
        )
        freed = result.rowcount or 0

        if freed == 0:
            added = await create_default_availability(db, doctor_id, days=1)
            print(f"No slots existed for today; created {added} default slot(s).")
        else:
            print(f"Marked {freed} slot(s) as available.")

        available = (
            await db.execute(
                select(DoctorAvailability.slot_time)
                .where(
                    DoctorAvailability.doctor_id == doctor_id,
                    DoctorAvailability.slot_date == today,
                    DoctorAvailability.status == "available",
                )
                .order_by(DoctorAvailability.slot_time)
            )
        ).scalars().all()
        if available:
            times = ", ".join(t.strftime("%I:%M %p").lstrip("0") for t in available)
            print(f"Available today: {times}")
        else:
            print("No available slots listed for today.")

        await db.commit()
        print("Done.")


if __name__ == "__main__":
    query = sys.argv[1] if len(sys.argv) > 1 else "Sharma"
    asyncio.run(free_today_slots(query))
