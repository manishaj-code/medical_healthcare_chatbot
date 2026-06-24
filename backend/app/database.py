"""Database config, session, security, dependencies, and logging."""

import logging
import sys
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, List
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import bcrypt
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

PHI_FIELDS = {"content", "ocr_text", "summary_text", "password", "token", "message"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    app_name: str = "AI Healthcare Assistant"
    log_level: str = "INFO"
    debug: bool = True
    sql_echo: bool = False

    database_url: str = "postgresql+asyncpg://healthcare:healthcare@localhost:5433/healthcare"
    database_pool_size: int = 10
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-to-a-64-char-random-string-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_expire_minutes: int = 30
    jwt_refresh_expire_days: int = 7

    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    llm_timeout_seconds: int = 30

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "medical-reports"
    s3_region: str = "us-east-1"
    s3_use_ssl: bool = False

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@mediai.com"
    dev_otp: bool = False
    bypass_otp: bool = False
    bypass_otp_code: str = "123456"

    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    guest_session_persist: bool = True
    clinic_timezone: str = "Asia/Kolkata"
    video_bypass_time_window: bool = False
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    rate_limit_chat_per_minute: int = 60
    rate_limit_auth_per_minute: int = 10
    secure_headers_enabled: bool = False

    transcript_enabled: bool = True
    transcript_stt_provider: str = "deepgram"
    transcript_chunk_bytes: int = 192_044
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-3"
    deepgram_language: str = "en"
    deepgram_smart_format: bool = True

    rag_enabled: bool = True
    rag_embedding_provider: str = "gemini"
    rag_embedding_model: str = "models/text-embedding-004"
    rag_embedding_dimensions: int = 768
    rag_top_k: int = 5

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors(cls, v: str) -> str:
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def redact_phi(data: dict[str, Any]) -> dict[str, Any]:
    redacted = {}
    for key, value in data.items():
        if key.lower() in PHI_FIELDS:
            redacted[key] = "[REDACTED]"
        elif isinstance(value, dict):
            redacted[key] = redact_phi(value)
        else:
            redacted[key] = value
    return redacted


def setup_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
    )


class Base(DeclarativeBase):
    pass


settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    echo=settings.sql_echo,
)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: UUID, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_expire_minutes)
    payload = {"sub": str(user_id), "role": role, "type": "access", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expire_days)
    payload = {"sub": str(user_id), "type": "refresh", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


def safe_decode_token(token: str) -> dict[str, Any] | None:
    try:
        return decode_token(token)
    except JWTError:
        return None


from app.models import Doctor, Patient, User  # noqa: E402
from app.models.enums import UserRole  # noqa: E402

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    payload = safe_decode_token(credentials.credentials)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def _role_value(role: UserRole | str) -> str:
    return role.value if isinstance(role, UserRole) else str(role)


def require_role(*roles: UserRole):
    allowed = {r.value for r in roles}

    async def checker(user: User = Depends(get_current_user)) -> User:
        if _role_value(user.role) not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return user

    return checker


require_patient = require_role(UserRole.patient)
require_doctor = require_role(UserRole.doctor)
require_admin = require_role(UserRole.admin)


async def get_patient_profile(user: User = Depends(require_patient), db: AsyncSession = Depends(get_db)) -> Patient:
    result = await db.execute(select(Patient).where(Patient.user_id == user.id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
    return patient


async def get_doctor_profile(user: User = Depends(require_doctor), db: AsyncSession = Depends(get_db)) -> Doctor:
    result = await db.execute(select(Doctor).where(Doctor.user_id == user.id))
    doctor = result.scalar_one_or_none()
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor profile not found")
    return doctor
