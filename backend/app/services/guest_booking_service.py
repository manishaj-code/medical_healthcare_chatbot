"""Guest landing chat — doctor booking and inline email/OTP verification."""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.auth_messages import EMAIL_ALREADY_EXISTS
from app.database import create_access_token, create_refresh_token, get_settings, hash_password
from app.models import Doctor, Patient, User
from app.models.enums import UserRole
from app.models.system import RefreshToken
from app.schemas.auth import UserResponse
from app.services.agent_tools import (
    match_slot_from_text,
    slot_for_storage,
    tool_book_slot,
    tool_get_doctor_slots,
    tool_search_doctors,
)
from app.services.chat_ui import (
    build_appointment_confirmed_ui,
    build_confirm_booking_ui,
    build_doctor_list_ui,
    build_slot_list_ui,
    doctor_list_intro,
    slot_list_intro,
)
from app.services.guest_session_store import migrate_guest_session, save_guest_session
from app.services.otp_service import (
    can_send_otp,
    generate_otp,
    mark_otp_sent,
    send_otp_email,
    store_otp,
    verify_otp,
)
from app.utils.email import normalize_email

START_FIND_DOCTOR_TOKEN = "[start_find_doctor]"
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_OTP_RE = re.compile(r"^\d{6}$")


def _yes(text: str) -> bool:
    return text.strip().lower() in {"yes", "yeah", "sure", "ok", "okay", "yep", "confirm", "yes please"}


def _no(text: str) -> bool:
    return text.strip().lower() in {"no", "nope", "nah", "not now", "later"}


def _name_from_email(email: str) -> str:
    local = email.split("@")[0]
    parts = [p for p in re.split(r"[._+\-]+", local) if p]
    if not parts:
        return "Patient"
    return " ".join(p[:1].upper() + p[1:].lower() if p else p for p in parts)


def is_find_doctor_start(text: str) -> bool:
    if text.strip() == START_FIND_DOCTOR_TOKEN:
        return True
    t = text.lower()
    return any(
        p in t
        for p in (
            "find a specialist",
            "find a doctor",
            "find doctor",
            "show doctors",
            "book appointment",
            "book an appointment",
            "see a doctor",
        )
    )


def in_guest_booking(session: dict) -> bool:
    if session.get("care_goal") != "guest_booking":
        return False
    awaiting = session.get("awaiting")
    if awaiting in {"pick_doctor", "pick_slot", "confirm_booking"}:
        return True
    return awaiting in {"guest_email", "guest_otp"} and bool(session.get("pending_slot"))


def _mentions_doctor_in_search(text: str, doctors: list[dict]) -> bool:
    t = text.lower()
    for d in doctors:
        name = d.get("name", "")
        last = name.split()[-1].lower().replace(".", "")
        if last and last in t:
            return True
        if name.lower() in t:
            return True
    return False


def is_booking_continuation_message(text: str, session: dict) -> bool:
    """True when the user is still trying to book (not changing topic)."""
    if is_find_doctor_start(text):
        return True
    awaiting = session.get("awaiting")
    if awaiting in ("confirm_booking", "guest_email", "guest_otp"):
        return True
    if awaiting == "offer_booking":
        return _yes(text) or _no(text)
    if session.get("care_goal") != "guest_booking":
        return False
    if awaiting not in ("pick_doctor", "pick_slot"):
        return False
    search = session.get("last_doctor_search") or {}
    doctors = search.get("doctors", [])
    all_slots = search.get("all_slots") or [s for d in doctors for s in d.get("slots", [])]
    if match_slot_from_text(text, all_slots):
        return True
    if _mentions_doctor_in_search(text, doctors):
        return True
    t = text.strip().lower()
    return any(p in t for p in ("show doctors", "another doctor", "different doctor", "more slots"))


def clear_abandoned_booking(session: dict, text: str) -> None:
    """Leave doctor-pick flow when the user sends an unrelated message."""
    if session.get("care_goal") != "guest_booking":
        return
    if session.get("awaiting") not in ("pick_doctor", "pick_slot"):
        return
    if is_booking_continuation_message(text, session):
        return
    session.pop("care_goal", None)
    session.pop("awaiting", None)
    session.pop("last_doctor_search", None)
    session.pop("pending_slot", None)
    session.pop("selected_doctor", None)


def in_booking_auth(session: dict) -> bool:
    return session.get("awaiting") in {"guest_email", "guest_otp"} and bool(session.get("pending_slot"))


async def _append_and_save(
    session_id: str,
    data: dict,
    session: dict,
    history: list,
    user_text: str,
    reply: str,
    *,
    agent: str = "guest_booking",
    ui: dict | None = None,
    extra: dict | None = None,
) -> dict[str, Any]:
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply, "agent": agent, "ui": ui})
    data["messages"] = history[-40:]
    data["session"] = session
    await save_guest_session(session_id, data)
    result: dict[str, Any] = {
        "reply": reply,
        "emergency": False,
        "agent": agent,
        "ui": ui,
        "requires_signup": False,
    }
    if extra:
        result.update(extra)
    return result


async def _show_doctors(db: AsyncSession, session: dict, specialty: str | None = None) -> tuple[str, dict | None]:
    search = await tool_search_doctors(db, specialty)
    session["last_doctor_search"] = search
    session["care_goal"] = "guest_booking"
    session["awaiting"] = "pick_doctor"
    session["recommended_specialty"] = specialty or "all"
    doctors = search.get("doctors", [])
    if not doctors:
        return "I couldn't find doctors with open slots right now. Please try again later.", None
    return doctor_list_intro(len(doctors)), build_doctor_list_ui(search)


async def _match_doctor(text: str, doctors: list[dict]) -> dict | None:
    t = text.lower()
    for d in doctors:
        name = d.get("name", "")
        last = name.split()[-1].lower().replace(".", "")
        if last and last in t:
            return d
        if name.lower() in t:
            return d
    return None


async def _issue_tokens(db: AsyncSession, user: User) -> tuple[str, str]:
    access = create_access_token(user.id, user.role)
    refresh = create_refresh_token(user.id)
    db.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hashlib.sha256(refresh.encode()).hexdigest(),
            expires_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()
    return access, refresh


async def _get_or_create_patient(db: AsyncSession, email: str) -> User:
    row = await db.execute(select(User).where(User.email == email))
    user = row.scalar_one_or_none()
    if user:
        if user.role != UserRole.patient.value:
            raise HTTPException(status_code=400, detail="This email is not a patient account.")
        return user

    name = _name_from_email(email)
    user = User(
        name=name,
        email=email,
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
    return user


async def _complete_booking(
    db: AsyncSession,
    session_id: str,
    session: dict,
    history: list,
    data: dict,
    user: User,
    user_text: str,
) -> dict[str, Any]:
    patient_row = await db.execute(select(Patient).where(Patient.user_id == user.id))
    patient = patient_row.scalar_one()
    pending = session.get("pending_slot")
    if not pending:
        return await _append_and_save(
            session_id, data, session, history, user_text,
            "Something went wrong with your booking. Please pick a time slot again.",
        )

    result = await tool_book_slot(db, patient, user.id, pending, None)
    access, refresh = await _issue_tokens(db, user)

    reply = (
        f"✅ **Appointment booked!**\n\n"
        f"**ID:** {result.get('apt_id')}\n"
        f"**Doctor:** {result.get('doctor_name')}\n"
        f"**When:** {result.get('label')}\n\n"
        f"Welcome, {user.name.split()[0]}! Your consultation is ready — see your appointment below."
    )
    ui = build_appointment_confirmed_ui(result)

    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply, "agent": "guest_booking", "ui": ui})
    data["messages"] = history[-40:]
    data["session"] = {}
    await save_guest_session(session_id, data)

    doctor_name = result.get("doctor_name", "Doctor")
    migrated = await migrate_guest_session(
        db,
        session_id,
        patient,
        title=f"Consultation — {doctor_name}",
    )

    return {
        "reply": reply,
        "emergency": False,
        "agent": "guest_booking",
        "ui": ui,
        "requires_signup": False,
        "auth_complete": True,
        "access_token": access,
        "refresh_token": refresh,
        "user": UserResponse.model_validate(user).model_dump(),
        "conversation_id": str(migrated.id) if migrated else None,
    }


async def _handle_guest_otp(
    db: AsyncSession,
    session_id: str,
    text: str,
    session: dict,
    history: list,
    data: dict,
) -> dict[str, Any]:
    email = session.get("guest_email")
    if not email or not _OTP_RE.match(text.strip()):
        return await _append_and_save(
            session_id,
            data,
            session,
            history,
            text,
            "Please enter the **6-digit code** we sent to your email.",
            extra={"awaiting_input": "otp"},
        )

    if not await verify_otp(email, text.strip()):
        return await _append_and_save(
            session_id,
            data,
            session,
            history,
            text,
            "That code is invalid or expired. Please try again or reply with your email to get a new code.",
            extra={"awaiting_input": "otp"},
        )

    user = await _get_or_create_patient(db, email)
    return await _complete_booking(db, session_id, session, history, data, user, text)


async def _handle_guest_email(
    db: AsyncSession,
    session_id: str,
    text: str,
    session: dict,
    history: list,
    data: dict,
) -> dict[str, Any]:
    email = normalize_email(text.strip())
    if not _EMAIL_RE.match(email):
        return await _append_and_save(
            session_id,
            data,
            session,
            history,
            text,
            "Please enter a valid **email address** (e.g. you@example.com).",
            extra={"awaiting_input": "email"},
        )

    if not await can_send_otp(email):
        return await _append_and_save(
            session_id,
            data,
            session,
            history,
            text,
            "Please wait a minute before requesting another code, then try your email again.",
            extra={"awaiting_input": "email"},
        )

    otp = generate_otp()
    await store_otp(email, otp)
    await mark_otp_sent(email)
    await send_otp_email(email, otp)

    session["guest_email"] = email
    session["awaiting"] = "guest_otp"
    settings = get_settings()
    booking_pending = bool(session.get("pending_slot"))
    action = "confirm your booking and sign in" if booking_pending else "verify your email and sign in"
    reply = (
        f"Thanks! We sent a **6-digit verification code** to **{email}**.\n\n"
        f"Enter the code here to {action}."
    )
    extra: dict[str, Any] = {"awaiting_input": "otp"}
    if settings.is_dev:
        extra["dev_otp"] = otp

    return await _append_and_save(session_id, data, session, history, text, reply, extra=extra)


async def process_guest_booking(
    db: AsyncSession,
    session_id: str,
    text: str,
    session: dict,
    history: list,
    data: dict,
) -> dict[str, Any] | None:
    if in_booking_auth(session):
        if session.get("awaiting") == "guest_otp":
            return await _handle_guest_otp(db, session_id, text, session, history, data)
        if session.get("awaiting") == "guest_email":
            return await _handle_guest_email(db, session_id, text, session, history, data)

    if is_find_doctor_start(text):
        reply, ui = await _show_doctors(db, session, None)
        return await _append_and_save(session_id, data, session, history, text, reply, ui=ui)

    if session.get("awaiting") == "offer_booking" and (
        _yes(text) or is_find_doctor_start(text)
    ):
        specialty = session.get("recommended_specialty")
        reply, ui = await _show_doctors(db, session, specialty if specialty != "General Physician" else None)
        return await _append_and_save(session_id, data, session, history, text, reply, ui=ui)

    if session.get("awaiting") == "offer_booking" and _no(text):
        session.pop("awaiting", None)
        session["booking_declined"] = True
        pname = session.get("_patient_first_name", "there")
        reply = (
            f"No problem, {pname}. Rest well and keep monitoring your symptoms. "
            "I'm here if you have more health questions."
        )
        return await _append_and_save(session_id, data, session, history, text, reply)

    if not in_guest_booking(session):
        return None

    awaiting = session.get("awaiting")

    if awaiting == "confirm_booking":
        if _no(text):
            session["awaiting"] = "pick_slot"
            session.pop("pending_slot", None)
            reply = "Booking cancelled. Pick another time or choose a different doctor."
            return await _append_and_save(session_id, data, session, history, text, reply)
        if _yes(text):
            pending = session.get("pending_slot") or {}
            session["awaiting"] = "guest_email"
            reply = (
                f"Almost done! To confirm **{pending.get('doctor_name', 'your doctor')}** "
                f"on **{pending.get('label', 'your selected time')}**, enter your **email address**.\n\n"
                "We'll send a one-time code to verify and complete your booking."
            )
            return await _append_and_save(
                session_id, data, session, history, text, reply, extra={"awaiting_input": "email"}
            )
        return await _append_and_save(
            session_id,
            data,
            session,
            history,
            text,
            "Please reply **Yes** to confirm this appointment or **No** to cancel.",
            ui=build_confirm_booking_ui("Guest", session.get("pending_slot", {}).get("doctor_name", ""), session.get("pending_slot", {}).get("label", "")),
        )

    search = session.get("last_doctor_search") or {}
    doctors = search.get("doctors", [])
    all_slots = search.get("all_slots") or [s for d in doctors for s in d.get("slots", [])]

    chosen_slot = match_slot_from_text(text, all_slots)
    if chosen_slot:
        stored = slot_for_storage(chosen_slot)
        session["pending_slot"] = stored
        session["awaiting"] = "confirm_booking"
        doc_name = stored.get("doctor_name", "")
        reply = (
            f"Please confirm your appointment:\n\n"
            f"**Doctor:** {doc_name}\n"
            f"**Time:** {stored.get('label')}\n\n"
            f"Reply **Yes** to continue."
        )
        ui = build_confirm_booking_ui("Guest", doc_name, stored.get("label", ""))
        return await _append_and_save(session_id, data, session, history, text, reply, ui=ui)

    if awaiting in ("pick_doctor", "pick_slot"):
        doc = await _match_doctor(text, doctors)
        if doc:
            slots_result = await tool_get_doctor_slots(db, UUID(str(doc["id"])))
            slots = slots_result.get("slots", [])
            if not slots:
                reply = f"No open slots for {doc['name']} right now."
                return await _append_and_save(session_id, data, session, history, text, reply)
            session["selected_doctor"] = {"id": str(doc["id"]), "name": doc["name"]}
            session["awaiting"] = "pick_slot"
            reply = slot_list_intro(doc["name"])
            ui = build_slot_list_ui(doc["name"], str(doc["id"]), slots)
            return await _append_and_save(session_id, data, session, history, text, reply, ui=ui)

    return None
