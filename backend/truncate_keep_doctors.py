"""Truncate operational data; keep doctor catalog (doctors, slots, specialties).

Run from backend/:  python truncate_keep_doctors.py
Docker:            docker compose exec api python truncate_keep_doctors.py
"""
import asyncio

from app.database import AsyncSessionLocal
from app.services.admin_service import truncate_keep_doctors


async def main() -> None:
    async with AsyncSessionLocal() as db:
        summary = await truncate_keep_doctors(db)
        await db.commit()
        print("Database reset complete (doctors preserved).")
        print(f"  Removed non-doctor users: {summary['removed_users']}")
        print(f"  Doctors in catalog: {summary['doctors_in_catalog']}")
        if summary["doctors_reseeded"]:
            print(f"  Re-seeded doctors: {summary['doctors_reseeded']}")
        print("  Doctor login: dr.sharma@clinic.com / Doctor@12345")


if __name__ == "__main__":
    asyncio.run(main())
