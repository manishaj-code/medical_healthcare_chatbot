from datetime import date
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.enums import UserRole
from app.schemas.common import ORMBase
from app.utils.email import normalize_email


def _normalize_email_field(value: str) -> str:
    return normalize_email(value)


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_register_email(cls, value: str) -> str:
        return _normalize_email_field(value)

    password: str = Field(min_length=8)
    role: UserRole = UserRole.patient
    specialty: str | None = Field(default=None, max_length=100)
    experience_years: int | None = Field(default=None, ge=0, le=50)

    @model_validator(mode="after")
    def doctor_requires_specialty(self) -> "RegisterRequest":
        if self.role == UserRole.doctor and not self.specialty:
            raise ValueError("Specialty is required when registering as a doctor")
        return self


class LoginRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_login_email(cls, value: str) -> str:
        return _normalize_email_field(value)

    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(ORMBase):
    id: UUID
    name: str
    email: str
    role: UserRole


class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_forgot_email(cls, value: str) -> str:
        return _normalize_email_field(value)


class ResetPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_reset_email(cls, value: str) -> str:
        return _normalize_email_field(value)
    otp: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8)


class PasswordResetMessage(BaseModel):
    message: str
    dev_otp: str | None = None


class ProfileUpdateRequest(BaseModel):
    name: str | None = None


class PatientProfileRequest(BaseModel):
    dob: date | None = None
    gender: str | None = None
    blood_group: str | None = None
    phone: str | None = None
    preferred_language: str = "en"
