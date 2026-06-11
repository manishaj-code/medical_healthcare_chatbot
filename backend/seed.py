"""Seed database — run from backend/ directory (also used by Docker entrypoint)."""
import asyncio

from sqlalchemy import select

from app.database import AsyncSessionLocal, hash_password
from app.models import Allergy, MedicalHistory, Medication, Patient, User
from app.models.enums import UserRole
from app.services.doctor_seed_service import seed_doctor_catalog

PATIENTS = [
    ("John Doe", "john@test.com", "diabetes"),
    ("Jane Smith", "jane@test.com", None),
    ("Alex Johnson", "alex@test.com", "hypertension"),
]


async def _user_exists(db, email: str) -> bool:
    result = await db.execute(select(User.id).where(User.email == email))
    return result.scalar_one_or_none() is not None


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        created_any = False

        if not await _user_exists(db, "admin@clinic.com"):
            db.add(
                User(
                    name="System Admin",
                    email="admin@clinic.com",
                    password_hash=hash_password("Admin@12345"),
                    role=UserRole.admin.value,
                )
            )
            created_any = True

        added_docs, updated_docs = await seed_doctor_catalog(db)
        if added_docs > 0 or updated_docs > 0:
            created_any = True

        for name, email, condition in PATIENTS:
            if await _user_exists(db, email):
                continue
            user = User(
                name=name,
                email=email,
                password_hash=hash_password("Patient@12345"),
                role=UserRole.patient.value,
            )
            db.add(user)
            await db.flush()
            patient = Patient(user_id=user.id, preferred_language="en")
            db.add(patient)
            await db.flush()
            if condition:
                db.add(
                    MedicalHistory(
                        patient_id=patient.id,
                        condition=condition.title(),
                        diagnosed_year=2020,
                    )
                )
            if email == "john@test.com":
                db.add(Allergy(patient_id=patient.id, allergen="Penicillin", severity="severe"))
                for med_name, dosage, frequency in (
                    ("Metformin", "500mg", "twice daily"),
                    ("Amlodipine", "5mg", "once daily"),
                    ("Atorvastatin", "10mg", "once at night"),
                ):
                    db.add(
                        Medication(
                            patient_id=patient.id,
                            name=med_name,
                            dosage=dosage,
                            frequency=frequency,
                            is_active=True,
                        )
                    )
            created_any = True

        if not created_any:
            print("Seed already applied, nothing new to add.")
            return

        await db.commit()
        print("Seed complete.")
        print(f"  Doctors added: {added_docs}, profiles updated: {updated_docs}")
        print("  Patient: john@test.com / Patient@12345")
        print("  Doctor:  dr.sharma@clinic.com / Doctor@12345")
        print("  Admin:   admin@clinic.com / Admin@12345")


if __name__ == "__main__":
    asyncio.run(seed())
