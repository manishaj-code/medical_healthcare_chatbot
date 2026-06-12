from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.utils.email import normalize_email


class ResetDataRequest(BaseModel):
    mode: Literal["keep_doctors", "all_data"] = Field(
        description="keep_doctors: remove patients and operational data; all_data: reset doctors too and re-seed catalog"
    )


class ResetDataResponse(BaseModel):
    mode: str
    removed_users: int
    doctors_in_catalog: int
    doctors_reseeded: int
    message: str


class DeleteAccountResponse(BaseModel):
    deleted_patient_id: str | None = None
    deleted_doctor_id: str | None = None
    email: str


class ClearDoctorAppointmentsResponse(BaseModel):
    doctor_id: str
    doctor_email: str
    deleted_appointments: int
    slots_freed: int
    message: str


class EmailTestRequest(BaseModel):
    email: EmailStr

    @field_validator("email", mode="before")
    @classmethod
    def normalize_test_email(cls, value: str) -> str:
        return normalize_email(value)


class EmailTestResponse(BaseModel):
    message: str
    mode: str
    dev_otp: str | None = None


class EmailStatusResponse(BaseModel):
    smtp_configured: bool
    smtp_host: str
    smtp_port: int
    smtp_from: str
