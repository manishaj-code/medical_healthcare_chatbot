"""Docker entrypoint: wait for DB, migrate, seed, start API."""
import asyncio
import os
import subprocess
import sys
import time

from sqlalchemy import text

from app.database import engine


async def wait_for_db(max_attempts: int = 30) -> None:
    for i in range(max_attempts):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            print("==> Database is ready.")
            return
        except Exception:
            print(f"    Database not ready, retrying... ({i + 1}/{max_attempts})")
            time.sleep(2)
    print("ERROR: Database not available.")
    sys.exit(1)


def run(cmd: list[str]) -> None:
    print(f"==> {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)


def main() -> None:
    print("==> MediAI startup")
    print("==> Waiting for database...")
    asyncio.run(wait_for_db())
    print("==> Running migrations...")
    run(["alembic", "upgrade", "head"])
    print("==> Checking seed data (skips if already up to date)...")
    run([sys.executable, "seed.py"])
    run([sys.executable, "seed_demo.py"])
    print("==> Starting API server on http://0.0.0.0:8000")
    os.execvp(
        "uvicorn",
        ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
    )


if __name__ == "__main__":
    main()
