"""In-chat doctor listing and appointment booking."""
import re
from datetime import date, time, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DoctorAvailability, Patient
from app.services.appointment_service import book_appointment
from app.services.doctor_service import list_doctors
from app.services.summary_service import prepare_appointment_summary


def _last_assistant_text(history: list[dict] | None) -> str:
    if not history:
        return ""
    for h in reversed(history):
        if str(h.get("role")) == "assistant":
            return h.get("content", "")
    return ""


def wants_to_book(user_message: str, history: list[dict] | None) -> bool:
    text = user_message.lower().strip()
    last = _last_assistant_text(history).lower()
    if text not in {"yes", "yeah", "sure", "ok", "okay", "please", "yes please"}:
        return False
    return (
        "book an appointment" in last
        or "book appointment" in last
        or "would you like to book" in last
        or "schedule an appointment" in last
        or "urgent care" in last
    )


def is_viewing_doctor_list(history: list[dict] | None) -> bool:
    last = _last_assistant_text(history).lower()
    return "available doctors" in last or "option number" in last or "time slots:" in last


async def get_doctors_with_slots(
    db: AsyncSession,
    specialty: str = "General Physician",
    max_doctors: int = 3,
    slots_per_doctor: int = 3,
) -> list[dict]:
    all_docs = await list_doctors(db)
    today = date.today()
    result = []
    for doc in all_docs:
        if specialty.lower() not in [s.lower() for s in doc["specializations"]] and specialty != "General Physician":
            continue
        rows = await db.execute(
            select(DoctorAvailability)
            .where(
                DoctorAvailability.doctor_id == doc["id"],
                DoctorAvailability.slot_date >= today,
                DoctorAvailability.status == "available",
            )
            .order_by(DoctorAvailability.slot_date, DoctorAvailability.slot_time)
            .limit(slots_per_doctor)
        )
        slots = []
        for s in rows.scalars().all():
            day_label = "Today" if s.slot_date == today else (
                "Tomorrow" if s.slot_date == today + timedelta(days=1) else str(s.slot_date)
            )
            t = s.slot_time
            hour = t.hour % 12 or 12
            ampm = "AM" if t.hour < 12 else "PM"
            time_label = f"{hour}:{t.minute:02d} {ampm}"
            slots.append({
                "doctor_id": doc["id"],
                "doctor_name": doc["name"],
                "slot_date": s.slot_date,
                "slot_time": s.slot_time,
                "label": f"{day_label}: {time_label}",
            })
        if slots:
            result.append({**doc, "slots": slots})
        if len(result) >= max_doctors:
            break
    return sorted(result, key=lambda d: (-d["rating"], -d["experience_years"]))


def format_doctors_slots_message(doctors: list[dict]) -> str:
    if not doctors:
        return (
            "I'm sorry, no doctors have open slots in the next few days. "
            "Please try again later or check the Doctors page for updates."
        )
    lines = ["Here are available doctors and time slots:\n"]
    option = 1
    for doc in doctors:
        spec = ", ".join(doc["specializations"])
        lines.append(f"{doc['name']} — {spec} (rating {doc['rating']})")
        for slot in doc["slots"]:
            lines.append(f"  {option}. {slot['label']}")
            option += 1
        lines.append("")
    lines.append(
        "Which would you prefer? Reply with the option number (e.g. 2) "
        "or say e.g. Dr. Sharma tomorrow 11 AM."
    )
    return "\n".join(lines)


def _flatten_options(doctors: list[dict]) -> list[dict]:
    options = []
    for doc in doctors:
        for slot in doc["slots"]:
            options.append(slot)
    return options


def _doctor_name_in_text(doctor_name: str, text: str) -> bool:
    normalized = text.lower()
    name = doctor_name.lower()
    last_name = name.split()[-1].replace(".", "")
    return (
        last_name in normalized
        or name.replace(".", "") in normalized.replace(".", "")
        or f"dr {last_name}" in normalized
        or f"dr. {last_name}" in normalized
    )


def _apply_ampm(hour: int, ampm: str | None) -> int:
    if ampm == "pm" and hour != 12:
        return hour + 12
    if ampm == "am" and hour == 12:
        return 0
    if ampm is None and 1 <= hour <= 6:
        return hour + 12  # clinic hours: bare afternoon time → PM
    return hour


def _parse_time_from_text(text: str) -> time | None:
    """Parse times like 4:00 PM, 4.00 PM, 4 PM, today: 4.00 pm."""
    t = text.lower().strip()
    # Normalize dot-separated times: 4.00 pm → 4:00 pm
    t = re.sub(r"(\d{1,2})\.(\d{2})\s*(am|pm)?", r"\1:\2 \3", t)

    m = re.search(r"(\d{1,2})\s*:\s*(\d{2})\s*(am|pm)?", t)
    if m:
        hour = _apply_ampm(int(m.group(1)), m.group(3))
        return time(hour, int(m.group(2)))

    m = re.search(r"(\d{1,2})\s*(am|pm)", t)
    if m:
        hour = _apply_ampm(int(m.group(1)), m.group(2))
        return time(hour, 0)

    return None


def _filter_by_day(pool: list[dict], text: str) -> list[dict]:
    if "today" in text:
        return [o for o in pool if "today" in o["label"].lower()]
    if "tomorrow" in text:
        return [o for o in pool if "tomorrow" in o["label"].lower()]
    return pool


def _choose_slot_from_text(text: str, options: list[dict]) -> tuple[dict | None, str | None]:
    """Match doctor + day + time from natural language. Returns (slot, hint_if_no_match)."""
    parsed_time = _parse_time_from_text(text)
    pool = options

    doctor_matches = [o for o in pool if _doctor_name_in_text(o["doctor_name"], text)]
    if doctor_matches:
        pool = doctor_matches

    pool = _filter_by_day(pool, text)

    if parsed_time:
        exact = [
            o for o in pool
            if o["slot_time"].hour == parsed_time.hour and o["slot_time"].minute == parsed_time.minute
        ]
        if len(exact) == 1:
            return exact[0], None
        if len(exact) > 1:
            return exact[0], None
        if doctor_matches:
            day_pool = _filter_by_day(doctor_matches, text)
            times = sorted({o["label"] for o in (day_pool or doctor_matches)})
            doc = doctor_matches[0]["doctor_name"]
            return None, (
                f"{doc} does not have a slot at that time. "
                f"Available: {', '.join(times)}. Please pick one or reply with an option number."
            )
        return None, "That time is not available. Please pick an option number from the list above."

    if len(pool) == 1:
        return pool[0], None

    if doctor_matches and len(pool) > 1:
        times = sorted({o["label"] for o in pool})
        return None, (
            f"Please specify the time for {doctor_matches[0]['doctor_name']} "
            f"(e.g. 2:00 PM) or reply with an option number. Available: {', '.join(times)}"
        )

    return None, None


def _parse_option_number(text: str) -> int | None:
    text = text.strip().lower()
    m = re.fullmatch(r"(\d+)", text)
    if m:
        return int(m.group(1))
    m = re.search(r"option\s*(\d+)", text)
    if m:
        return int(m.group(1))
    return None


async def try_book_from_chat(
    db: AsyncSession,
    patient: Patient,
    user_id: UUID,
    message: str,
    history: list[dict] | None,
    conversation_id: UUID | None = None,
    specialty: str = "General Physician",
) -> str | None:
    if not is_viewing_doctor_list(history):
        return None

    doctors = await get_doctors_with_slots(db, specialty)
    options = _flatten_options(doctors)
    if not options:
        return None

    text = message.lower().strip()
    chosen = None

    option_num = _parse_option_number(text)
    if option_num is not None:
        idx = option_num - 1
        if 0 <= idx < len(options):
            chosen = options[idx]

    if not chosen:
        chosen, hint = _choose_slot_from_text(text, options)
        if hint:
            return hint

    if not chosen and len(options) == 1:
        if text in {"yes", "yeah", "sure", "ok", "book it", "confirm"}:
            chosen = options[0]

    if not chosen:
        return (
            "I couldn't match that to an available slot. Please reply with an option number "
            "(e.g. 1 or 2) from the list above, or say e.g. Dr. Sharma today 2:00 PM."
        )

    try:
        appt = await book_appointment(
            db,
            patient.id,
            chosen["doctor_id"],
            chosen["slot_date"],
            chosen["slot_time"],
            user_id,
        )
        try:
            await prepare_appointment_summary(db, appt.id, conversation_id)
        except Exception:
            pass
        return (
            f"Appointment booked successfully!\n\n"
            f"Doctor: {chosen['doctor_name']}\n"
            f"Date & Time: {chosen['label']}\n"
            f"Status: Confirmed\n\n"
            f"You will receive a confirmation notification. "
            f"Your doctor will receive an AI summary of your symptoms before the visit."
        )
    except HTTPException as e:
        detail = e.detail if isinstance(e.detail, str) else str(e.detail)
        return f"Sorry, that slot could not be booked ({detail}). Please pick another option."
    except Exception as e:
        return f"Sorry, that slot could not be booked. Please pick another option."


async def build_booking_list_reply(db: AsyncSession, specialty: str = "General Physician") -> str:
    doctors = await get_doctors_with_slots(db, specialty)
    return format_doctors_slots_message(doctors)
