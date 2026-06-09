from typing import Literal

from pydantic import BaseModel, Field


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
