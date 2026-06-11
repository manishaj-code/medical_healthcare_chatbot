import hashlib
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.auth_messages import EMAIL_ALREADY_EXISTS
from app.utils.email import normalize_email

from app.database import (
    create_access_token,
    create_refresh_token,
    hash_password,
    safe_decode_token,
    verify_password,
)
from app.models import Doctor, DoctorSpecialization, Patient, User
from app.models.enums import UserRole
from app.models.system import RefreshToken
from app.database import get_settings
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.doctor_service import create_default_availability, get_or_create_specialization
from app.services.otp_service import (
    can_send_password_reset_otp,
    generate_otp,
    mark_password_reset_otp_sent,
    send_password_reset_email,
    store_password_reset_otp,
    verify_password_reset_otp,
)


async def register_user(db: AsyncSession, data: RegisterRequest) -> User:
    email = normalize_email(data.email)
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=EMAIL_ALREADY_EXISTS)
    if data.role == UserRole.admin:
        raise HTTPException(status_code=403, detail="Cannot self-register as admin")
    user = User(
        name=data.name,
        email=email,
        password_hash=hash_password(data.password),
        role=data.role.value,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=400, detail=EMAIL_ALREADY_EXISTS) from None
    if data.role == UserRole.patient:
        db.add(Patient(user_id=user.id))
    elif data.role == UserRole.doctor:
        specialty = data.specialty or "General Physician"
        doc = Doctor(
            user_id=user.id,
            experience_years=data.experience_years or 1,
            rating=4.5,
            bio=f"{specialty} — registered via application",
            is_verified=True,
        )
        db.add(doc)
        await db.flush()
        spec = await get_or_create_specialization(db, specialty)
        db.add(DoctorSpecialization(doctor_id=doc.id, specialization_id=spec.id))
        await create_default_availability(db, doc.id)
    await db.flush()
    return user


async def login_user(db: AsyncSession, data: LoginRequest) -> tuple[str, str, User]:
    email = normalize_email(data.email)
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    user.last_login = datetime.now(timezone.utc)
    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hashlib.sha256(refresh.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc),
        )
    )
    return access, refresh, user


async def request_password_reset(db: AsyncSession, email: str) -> str | None:
    email = normalize_email(email)
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        return None
    if not await can_send_password_reset_otp(email):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait a minute before requesting another code.",
        )
    otp = generate_otp()
    await store_password_reset_otp(email, otp)
    await mark_password_reset_otp_sent(email)
    await send_password_reset_email(email, otp)
    settings = get_settings()
    return otp if settings.dev_otp else None


async def reset_password(db: AsyncSession, email: str, otp: str, new_password: str) -> None:
    email = normalize_email(email)
    if not await verify_password_reset_otp(email, otp):
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(new_password)
    await db.flush()


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> str:
    payload = safe_decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id = UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return create_access_token(user.id, user.role)
