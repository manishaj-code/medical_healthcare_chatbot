"""Email verification for guest chat before patient-specific actions."""
from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.auth_messages import EMAIL_ALREADY_EXISTS
from app.healthcare_policy import patient_first_name
from app.database import create_access_token, create_refresh_token, get_settings, hash_password
from app.models import Patient, User
from app.models.enums import UserRole
from app.models.system import RefreshToken
from app.multi_agent.types import AgentResponse
from app.schemas.auth import UserResponse
from app.services.flow_state import get_flow, set_flow
from app.services.guest_flow import guest_flow_conversation_id
from app.services.guest_resume_service import build_resume_prompt, prepare_resume_session
from app.services.guest_session_store import migrate_guest_session, save_guest_session
from app.utils.email import normalize_email
from app.services.otp_service import (
    can_send_otp,
    generate_otp,
    mark_otp_sent,
    send_otp_email,
    store_otp,
    verify_otp,
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_OTP_RE = re.compile(r"^\d{6}$")

GUEST_AUTH_AWAITING = frozenset({"guest_email", "guest_otp"})

ACTION_LABELS = {
    "book": "confirm your appointment",
    "cancel": "cancel your appointment",
    "reschedule": "reschedule your appointment",
    "refill": "request a prescription refill",
}


def in_guest_auth(session: dict) -> bool:
    return session.get("awaiting") in GUEST_AUTH_AWAITING


def in_guest_auth_flow(session: dict) -> bool:
    """True when verifying email for a pending patient action."""
    return in_guest_auth(session) and bool(session.get("pending_auth_action"))


def _name_from_email(email: str) -> str:
    local = email.split("@")[0]
    parts = [p for p in re.split(r"[._+\-]+", local) if p]
    if not parts:
        return "Patient"
    return " ".join(p[:1].upper() + p[1:].lower() if p else p for p in parts)


def guest_auth_gate(ctx, action: str, detail: str | None = None) -> AgentResponse:
    """Prompt guest for email before completing a patient-specific action."""
    pname = patient_first_name(ctx.patient_ctx.get("name"))
    label = ACTION_LABELS.get(action, "continue")
    detail_line = f" for **{detail}**" if detail else ""
    opener = f"Almost done, {pname}!" if pname != "there" else "Almost done!"
    return AgentResponse(
        reply=(
            f"{opener} To {label}{detail_line}, please provide your **email address**.\n\n"
            "We'll send a secure one-time verification code. After verification you'll be signed in "
            "to the Patient Portal to complete this step."
        ),
        agent="scheduling_agent" if action in ("book", "cancel", "reschedule") else "refill_agent",
        session_patch={
            "awaiting": "guest_email",
            "pending_auth_action": action,
            "care_goal": "guest_verify",
        },
    )


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


async def _append_and_save(
    session_id: str,
    data: dict,
    session: dict,
    history: list,
    user_text: str,
    reply: str,
    *,
    agent: str = "guest_auth",
    ui: dict | None = None,
    extra: dict | None = None,
) -> dict[str, Any]:
    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply, "agent": agent, "ui": ui})
    data["messages"] = history[-40:]
    data["session"] = session
    await save_guest_session(session_id, data)
    await set_flow(guest_flow_conversation_id(session_id), {"session": session})
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


async def _sync_guest_flow_session(session_id: str, session: dict) -> dict:
    """Merge supervisor flow state into guest session before auth completion."""
    flow = await get_flow(guest_flow_conversation_id(session_id))
    merged = dict(flow.get("session") or {})
    merged.update(session)
    return merged


async def _complete_guest_verification(
    db: AsyncSession,
    session_id: str,
    session: dict,
    history: list,
    data: dict,
    user: User,
    user_text: str,
) -> dict[str, Any]:
    """Migrate guest chat to patient portal without executing the pending action."""
    patient_row = await db.execute(select(Patient).where(Patient.user_id == user.id))
    patient = patient_row.scalar_one()

    session = await _sync_guest_flow_session(session_id, session)
    action = session.get("pending_auth_action") or "book"
    session = prepare_resume_session(session, action)

    action_messages = {
        "book": "Your appointment details are saved — I'll finish booking in the Patient Portal.",
        "cancel": "Your cancellation request is ready — I'll complete it in the Patient Portal.",
        "reschedule": "Your new time slot is saved — I'll finish rescheduling in the Patient Portal.",
        "refill": "Your refill request is ready — I'll submit it in the Patient Portal.",
    }
    reply = (
        f"✅ **Email verified!** Welcome, {user.name.split()[0]}.\n\n"
        f"{action_messages.get(action, 'Continuing your consultation in the Patient Portal.')}\n\n"
        "_Taking you to your consultation now…_"
    )

    history.append({"role": "user", "content": user_text})
    history.append({"role": "assistant", "content": reply, "agent": "guest_auth"})
    data["messages"] = history[-40:]
    data["session"] = session
    await save_guest_session(session_id, data)

    migrated = await migrate_guest_session(db, session_id, patient)

    access, refresh = await _issue_tokens(db, user)

    resume_prompt = build_resume_prompt(session)

    return {
        "reply": reply,
        "emergency": False,
        "agent": "guest_auth",
        "ui": None,
        "requires_signup": False,
        "auth_complete": True,
        "access_token": access,
        "refresh_token": refresh,
        "user": UserResponse.model_validate(user).model_dump(),
        "conversation_id": str(migrated.id) if migrated else None,
        "resume_prompt": resume_prompt,
        "pending_auth_action": action,
    }


async def process_guest_auth_turn(
    db: AsyncSession,
    session_id: str,
    text: str,
    session: dict,
    history: list,
    data: dict,
) -> dict[str, Any] | None:
    """Handle guest email / OTP verification turns. Returns None if not in auth flow."""
    if not in_guest_auth(session):
        return None

    if session.get("awaiting") == "guest_otp":
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
        return await _complete_guest_verification(db, session_id, session, history, data, user, text)

    if session.get("awaiting") == "guest_email":
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
        reply = (
            f"Thanks! We sent a **6-digit verification code** to **{email}**.\n\n"
            "Enter the code here to verify your identity and continue in the Patient Portal."
        )
        extra: dict[str, Any] = {"awaiting_input": "otp"}
        if settings.dev_otp:
            extra["dev_otp"] = otp

        return await _append_and_save(session_id, data, session, history, text, reply, extra=extra)

    return None
