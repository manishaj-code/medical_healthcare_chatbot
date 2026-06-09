"""Seed database — run from backend/ directory (also used by Docker entrypoint)."""
import asyncio

from sqlalchemy import select

from app.database import AsyncSessionLocal, hash_password
from app.models import (
    Allergy,
    Doctor,
    DoctorSpecialization,
    MedicalHistory,
    Medication,
    Patient,
    User,
)
from app.models.enums import UserRole
from app.services.doctor_service import create_default_availability, get_or_create_specialization

SPECIALTIES = ["General Physician", "Cardiologist", "Neurologist", "Dermatologist", "Pediatrician"]
DOCTORS = [
    ("Dr. Sharma", "dr.sharma@clinic.com", "General Physician", 15, 4.8),
    ("Dr. Patel", "dr.patel@clinic.com", "Cardiologist", 12, 4.7),
    ("Dr. Kumar", "dr.kumar@clinic.com", "Neurologist", 10, 4.6),
    ("Dr. Singh", "dr.singh@clinic.com", "Dermatologist", 8, 4.5),
    ("Dr. Reddy", "dr.reddy@clinic.com", "Pediatrician", 20, 4.9),
]
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

        spec_map = {}
        for name in SPECIALTIES:
            spec_map[name] = await get_or_create_specialization(db, name)
        await db.flush()

        new_doctors: list[Doctor] = []
        for name, email, specialty, exp, rating in DOCTORS:
            if await _user_exists(db, email):
                continue
            user = User(
                name=name,
                email=email,
                password_hash=hash_password("Doctor@12345"),
                role=UserRole.doctor.value,
            )
            db.add(user)
            await db.flush()
            doc = Doctor(
                user_id=user.id,
                experience_years=exp,
                rating=rating,
                bio=f"Experienced {specialty}",
            )
            db.add(doc)
            await db.flush()
            db.add(DoctorSpecialization(doctor_id=doc.id, specialization_id=spec_map[specialty].id))
            new_doctors.append(doc)
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
                db.add(
                    Medication(
                        patient_id=patient.id,
                        name="Amlodipine",
                        dosage="5mg",
                        frequency="daily",
                        is_active=True,
                    )
                )
            created_any = True

        await db.flush()
        for doc in new_doctors:
            await create_default_availability(db, doc.id)

        if not created_any:
            print("Seed already applied, nothing new to add.")
            return

        await db.commit()
        print("Seed complete.")
        print("  Patient: john@test.com / Patient@12345")
        print("  Doctor:  dr.sharma@clinic.com / Doctor@12345")
        print("  Admin:   admin@clinic.com / Admin@12345")


if __name__ == "__main__":
    asyncio.run(seed())
