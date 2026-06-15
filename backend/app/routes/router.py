from fastapi import APIRouter

from app.routes import (
    admin,
    appointments,
    auth,
    chat,
    doctor_portal,
    doctors,
    guest,
    patients,
    reports,
    symptoms,
    urgent_consult,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(guest.router)
api_router.include_router(patients.router)
api_router.include_router(chat.router)
api_router.include_router(symptoms.router)
api_router.include_router(doctors.router)
api_router.include_router(appointments.router)
api_router.include_router(urgent_consult.router)
api_router.include_router(reports.router)
api_router.include_router(doctor_portal.router)
api_router.include_router(admin.router)
