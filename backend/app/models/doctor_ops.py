import uuid
from datetime import date, datetime, time

from sqlalchemy import Date, ForeignKey, Integer, String, Text, Time, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import AppointmentStatus


class Specialization(Base):
    __tablename__ = "specializations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class DoctorSpecialization(Base):
    __tablename__ = "doctor_specializations"

    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id"), primary_key=True)
    specialization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("specializations.id"), primary_key=True
    )


class DoctorAvailability(Base):
    __tablename__ = "doctor_availability"
    __table_args__ = (UniqueConstraint("doctor_id", "slot_date", "slot_time", name="uq_doctor_slot"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id"), index=True)
    slot_date: Mapped[date] = mapped_column(Date, nullable=False)
    slot_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="available")


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("patients.id"), index=True)
    doctor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("doctors.id"), index=True)
    slot_date: Mapped[date] = mapped_column(Date, nullable=False)
    slot_time: Mapped[time] = mapped_column(Time, nullable=False)
    status: Mapped[AppointmentStatus] = mapped_column(String(20), default=AppointmentStatus.confirmed)
    rescheduled_from_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
