import hashlib
import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.auth_messages import EMAIL_ALREADY_EXISTS
from app.database import (
    create_access_token,
    create_refresh_token,
    get_db,
    get_settings,
    hash_password,
)
from app.models import Patient, User
from app.models.enums import UserRole
from app.utils.email import normalize_email
from app.models.system import RefreshToken
from app.schemas.auth import TokenResponse, UserResponse
from app.schemas.common import ResponseEnvelope
from app.services.guest_chat_service import process_guest_message
from app.services.guest_report_service import process_guest_report_upload
from app.services.guest_session_store import create_guest_session, migrate_guest_session
from app.services.otp_service import (
    can_send_otp,
    generate_otp,
    mark_otp_sent,
    send_otp_email,
    store_otp,
    verify_otp,
)
router = APIRouter(prefix="/guest", tags=["guest"])


class GuestSessionResponse(BaseModel):
    session_id: str


class GuestMessageCreate(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=2000)


class GuestChatReply(BaseModel):
    reply: str
    emergency: bool = False
    agent: str = "guest"
    ui: dict | None = None
    requires_signup: bool = False
    signup_reason: str | None = None
    awaiting_input: str | None = None  # email | otp | upload
    dev_otp: str | None = None
    auth_complete: bool = False
    access_token: str | None = None
    refresh_token: str | None = None
    user: dict | None = None
    conversation_id: str | None = None


class SendOtpRequest(BaseModel):
    email: EmailStr
    session_id: str | None = None
    name: str | None = Field(default=None, min_length=2, max_length=255)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        return normalize_email(value)


class SendOtpResponse(BaseModel):
    message: str
    dev_otp: str | None = None


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6)
    session_id: str | None = None
    name: str = Field(min_length=2, max_length=255)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        return normalize_email(value)


class VerifyOtpResponse(TokenResponse):
    user: UserResponse
    conversation_id: UUID | None = None


@router.post("/session", response_model=ResponseEnvelope[GuestSessionResponse])
async def start_guest_session():
    session_id = await create_guest_session()
    return ResponseEnvelope(data=GuestSessionResponse(session_id=session_id))


@router.post("/chat/messages", response_model=ResponseEnvelope[GuestChatReply])
async def guest_chat_message(data: GuestMessageCreate, db: AsyncSession = Depends(get_db)):
    try:
        result = await process_guest_message(data.session_id, data.message, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Guest chat processing failed.") from None
    return ResponseEnvelope(data=GuestChatReply(**result))


@router.post("/report-upload", response_model=ResponseEnvelope[GuestChatReply])
async def guest_report_upload(
    session_id: str = Form(...),
    file: UploadFile = File(...),
):
    try:
        data = await file.read()
        result = await process_guest_report_upload(
            session_id,
            data,
            file.filename or "report.pdf",
            file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        raise HTTPException(status_code=500, detail="Report upload failed.") from None
    return ResponseEnvelope(data=GuestChatReply(**result))


@router.post("/auth/send-otp", response_model=ResponseEnvelope[SendOtpResponse])
async def send_otp(data: SendOtpRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=EMAIL_ALREADY_EXISTS)

    if not await can_send_otp(data.email):
        raise HTTPException(status_code=429, detail="Please wait a minute before requesting another code.")

    otp = generate_otp()
    await store_otp(data.email, otp)
    await mark_otp_sent(data.email)
    await send_otp_email(data.email, otp)

    settings = get_settings()
    payload = SendOtpResponse(
        message=f"Verification code sent to {data.email}.",
        dev_otp=otp if settings.is_dev else None,
    )
    return ResponseEnvelope(data=payload)


@router.post("/auth/verify-otp", response_model=ResponseEnvelope[VerifyOtpResponse])
async def verify_otp_and_register(data: VerifyOtpRequest, db: AsyncSession = Depends(get_db)):
    if not await verify_otp(data.email, data.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")

    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user:
        raise HTTPException(status_code=400, detail=EMAIL_ALREADY_EXISTS)

    user = User(
        name=data.name.strip(),
        email=data.email,
        password_hash=hash_password(secrets.token_urlsafe(24)),
        role=UserRole.patient.value,
    )
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status_code=400, detail=EMAIL_ALREADY_EXISTS) from None
    db.add(Patient(user_id=user.id))
    await db.flush()
    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hashlib.sha256(refresh.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc),
        )
    )

    patient_row = await db.execute(select(Patient).where(Patient.user_id == user.id))
    patient = patient_row.scalar_one_or_none()
    migrated_conv = None
    if patient and data.session_id:
        migrated_conv = await migrate_guest_session(db, data.session_id, patient)

    return ResponseEnvelope(
        data=VerifyOtpResponse(
            access_token=access,
            refresh_token=refresh,
            user=UserResponse.model_validate(user),
            conversation_id=migrated_conv.id if migrated_conv else None,
        )
    )
