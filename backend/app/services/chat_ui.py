"""Structured UI payloads for interactive chat (doctor/slot pickers)."""


def build_doctor_list_ui(result: dict) -> dict | None:
    doctors = [d for d in result.get("doctors", []) if d.get("slots")]
    if not doctors:
        return None
    return {
        "type": "doctor_list",
        "total": len(doctors),
        "doctors": [
            {
                "id": d["id"],
                "name": d["name"],
                "specialty": d.get("specialty", "General Physician"),
                "experience_years": d.get("experience_years", 0),
                "rating": d.get("rating"),
                "profile_image_url": d.get("profile_image_url"),
                "consultation_fee": d.get("consultation_fee"),
                "hospital_name": d.get("hospital_name"),
                "professional_summary": d.get("professional_summary") or d.get("bio"),
                "next_available": d.get("next_available"),
                "slots": [
                    {
                        "label": s["label"],
                        "doctor_id": s.get("doctor_id", d["id"]),
                        "doctor_name": s.get("doctor_name", d["name"]),
                        "slot_date": s.get("slot_date"),
                        "slot_time": s.get("slot_time"),
                        "message": f"{d['name']} {s['label']}",
                    }
                    for s in d.get("slots", [])  # send all slots, no cap here
                ],
            }
            for d in doctors
        ],
    }


def _slot_entries(doctor_name: str, doctor_id: str, slots: list[dict]) -> list[dict]:
    return [
        {
            "label": s["label"],
            "doctor_id": s.get("doctor_id", doctor_id),
            "doctor_name": s.get("doctor_name", doctor_name),
            "slot_date": s.get("slot_date"),
            "slot_time": s.get("slot_time"),
            "message": s["label"],
        }
        for s in slots
    ]


def build_slot_list_ui(doctor_name: str, doctor_id: str, slots: list[dict]) -> dict | None:
    if not slots:
        return None
    return {
        "type": "slot_list",
        "doctor_id": doctor_id,
        "doctor_name": doctor_name,
        "slots": _slot_entries(doctor_name, doctor_id, slots),
    }


def build_reschedule_slots_ui(
    apt_id: str,
    doctor_name: str,
    doctor_id: str,
    current_time: str,
    slots: list[dict],
) -> dict | None:
    if not slots:
        return None
    return {
        "type": "reschedule_slots",
        "apt_id": apt_id,
        "doctor_id": doctor_id,
        "doctor_name": doctor_name,
        "current_time": current_time,
        "slots": _slot_entries(doctor_name, doctor_id, slots),
    }


def doctor_list_intro(count: int) -> str:
    noun = "doctor" if count == 1 else "doctors"
    return f"I found **{count} {noun}** with open time slots."


def slot_list_intro(doctor_name: str) -> str:
    return f"Pick a time with **{doctor_name}**."


def build_appointment_confirmed_ui(result: dict) -> dict | None:
    if not result.get("appointment_id"):
        return None
    from app.services.appointment_card_service import build_appointment_confirmed_ui as _build_card

    return _build_card(
        appointment_id=str(result["appointment_id"]),
        apt_id=result.get("apt_id", ""),
        doctor_name=result.get("doctor_name", "Doctor"),
        label=result.get("label", ""),
        specialty=result.get("specialty", "General Physician"),
        hospital_name=result.get("hospital_name"),
        status=result.get("status", "confirmed"),
        reminder_set=bool(result.get("reminder_set")),
    )


def _choice_options(pairs: list[tuple[str, str]]) -> list[dict]:
    return [{"label": label, "message": message} for label, message in pairs]


def build_confirm_booking_ui(patient_name: str, doctor_name: str, slot_label: str) -> dict:
    return {
        "type": "confirm_booking",
        "patient_name": patient_name,
        "doctor_name": doctor_name,
        "label": slot_label,
        "options": _choice_options([
            ("Yes, confirm booking", "Yes"),
            ("No, cancel", "No"),
        ]),
    }


def build_confirm_reschedule_ui(current_label: str, new_label: str) -> dict:
    return {
        "type": "confirm_reschedule",
        "current": current_label,
        "label": new_label,
        "options": _choice_options([
            ("Yes, confirm", "Yes"),
            ("No, keep current time", "No"),
        ]),
    }


def build_yes_no_ui(
    yes_label: str = "Yes",
    yes_message: str = "Yes",
    no_label: str = "No",
    no_message: str = "No",
) -> dict:
    return {
        "type": "yes_no",
        "options": _choice_options([(yes_label, yes_message), (no_label, no_message)]),
    }


def build_action_menu_ui(
    options: list[tuple[str, str]],
    *,
    menu_type: str = "action_menu",
    variant: str = "stack",
) -> dict:
    return {
        "type": menu_type,
        "variant": variant,
        "options": _choice_options(options),
    }


def build_aura_welcome_actions_ui() -> dict:
    return build_action_menu_ui(
        [
            ("🩺 Check My Symptoms", "[start_symptom_triage]"),
            ("👨‍⚕️ Find a Specialist Doctor", "[start_find_doctor]"),
            ("📄 Explain My Medical Report", "[start_explain_report]"),
        ],
        menu_type="welcome_actions",
        variant="stack",
    )


def build_symptom_picker_ui() -> dict:
    return build_aura_symptom_picker_ui()


def build_aura_symptom_picker_ui() -> dict:
    return {
        "type": "symptom_picker",
        "variant": "stack",
        "options": _choice_options([
            ("🤒 Fever", "Fever"),
            ("🤧 Cold & Cough", "Cold and cough"),
            ("🤕 Headache", "Headache"),
            ("🤢 Stomach Pain", "Stomach pain"),
            ("❤️ Chest Pain", "Chest pain"),
            ("🫁 Breathing Problem", "Breathing problem"),
            ("🤒 Skin Problem", "Skin problem"),
            ("🦴 Joint Pain", "Joint pain"),
            ("👁️ Eye Problem", "Eye problem"),
            ("📝 Type My Own Symptoms", "[aura_type_symptoms]"),
            ("📷 Upload Symptom Photo", "[aura_upload_symptom_image]"),
        ]),
    }


def build_symptom_image_hint_ui() -> dict:
    return build_action_menu_ui(
        [("📷 Choose Photo", "[aura_upload_symptom_image]")],
        menu_type="symptom_image_hint",
        variant="stack",
    )


def build_video_consultation_ui(join_url: str, apt_id: str, doctor_name: str) -> dict:
    return {
        "type": "video_consultation",
        "join_url": join_url,
        "apt_id": apt_id,
        "doctor_name": doctor_name,
        "options": _choice_options([
            ("Join Video Call", join_url),
            ("Not now", "Not now"),
        ]),
    }


def build_symptom_starter_ui() -> dict:
    """First triage turn — common complaints; user can also type freely."""
    return build_action_menu_ui(
        [
            ("Fever", "I have a fever"),
            ("Headache", "I have a headache"),
            ("Cough", "I have a cough"),
            ("Stomach pain", "I have stomach pain"),
        ],
        menu_type="symptom_starter",
        variant="stack",
    )


def build_duration_picker_ui() -> dict:
    return {
        "type": "duration_picker",
        "variant": "stack",
        "options": _choice_options([
            ("Less than 1 day", "Less than 1 day"),
            ("1–3 days", "1-3 days"),
            ("4–7 days", "4-7 days"),
            ("Over 1 week", "Over 1 week"),
            ("Not sure", "Not sure"),
        ]),
    }


def build_severity_picker_ui() -> dict:
    return {
        "type": "severity_picker",
        "variant": "stack",
        "options": _choice_options([
            ("Mild", "Mild"),
            ("Moderate", "Moderate"),
            ("Severe", "Severe"),
            ("Not sure", "Not sure"),
        ]),
    }


def infer_triage_quick_actions(reply: str, session: dict) -> tuple[dict | None, dict]:
    """Attach contextual quick buttons when the assistant asks a structured triage question."""
    if session.get("triage_assessed"):
        return None, {}
    lower = (reply or "").lower()
    if any(
        phrase in lower
        for phrase in (
            "other symptom",
            "any other",
            "anything else",
            "additional symptom",
            "noticed any other",
        )
    ):
        if any(
            hint in lower
            for hint in (
                "type them below",
                "type freely below",
                "please type the other symptoms",
            )
        ):
            return None, {}
        return build_more_symptoms_ui(), {
            "awaiting": "more_symptoms",
            "care_goal": "symptom_assessment",
            "active_specialist": "triage_agent",
        }
    if "how long" in lower or "how many days" in lower:
        return build_duration_picker_ui(), {
            "awaiting": "pick_duration",
            "care_goal": "symptom_assessment",
            "active_specialist": "triage_agent",
        }
    if "severe" in lower or "severity" in lower or "describe the severity" in lower:
        return build_severity_picker_ui(), {
            "awaiting": "pick_severity",
            "care_goal": "symptom_assessment",
            "active_specialist": "triage_agent",
        }
    if "would you like to book an appointment" in lower:
        return build_post_assessment_ui(), {
            "awaiting": "offer_booking",
            "care_goal": "symptom_assessment",
            "active_specialist": "triage_agent",
        }
    return None, {}


def build_more_symptoms_ui() -> dict:
    ui = build_yes_no_ui(
        yes_label="Yes, more symptoms",
        yes_message="Yes, I have more symptoms",
        no_label="No, that's all",
        no_message="No other symptoms",
    )
    ui["type"] = "more_symptoms"
    ui["variant"] = "stack"
    return ui


def build_no_more_symptoms_ui() -> dict:
    """After patient confirmed more symptoms — only offer to finish (no Yes loop)."""
    return {
        "type": "more_symptoms",
        "variant": "stack",
        "options": _choice_options([
            ("No, that's all", "No other symptoms"),
        ]),
    }


def build_urgent_consult_pending_ui(payload: dict) -> dict:
    return {
        "type": "urgent_consult_pending",
        "request_id": payload.get("id"),
        "specialty": payload.get("specialty"),
        "status": payload.get("status", "pending"),
        "risk_level": payload.get("risk_level"),
        "symptoms": payload.get("symptoms") or [],
        "doctors": payload.get("doctors") or [],
        "expires_at": payload.get("expires_at"),
    }


def build_urgent_consult_accepted_ui(payload: dict) -> dict:
    return {
        "type": "urgent_consult_accepted",
        "request_id": payload.get("id"),
        "status": "assigned",
        "specialty": payload.get("specialty"),
        "appointment_id": payload.get("appointment_id"),
        "apt_id": payload.get("apt_id"),
        "doctor_name": payload.get("accepted_doctor_name") or payload.get("doctor_name"),
        "join_url": payload.get("join_url"),
        "symptoms": payload.get("symptoms") or [],
    }


def build_post_assessment_ui() -> dict:
    return build_action_menu_ui(
        [
            ("Self-care tips", "Tell me self-care advice for my symptoms"),
            ("Book appointment", "Book appointment"),
        ],
        menu_type="post_assessment",
        variant="stack",
    )


def build_post_self_care_ui() -> dict:
    """After self-care advice was shown - offer booking only, not self-care again."""
    return build_action_menu_ui(
        [("Book appointment", "Book appointment")],
        menu_type="post_assessment",
        variant="stack",
    )


def build_find_doctor_menu_ui() -> dict:
    return build_action_menu_ui(
        [
            ("By Symptoms", "[aura_find_by_symptoms]"),
            ("By Specialty", "[aura_find_by_specialty]"),
            ("Near Me", "[aura_find_near_me]"),
            ("View All Doctors", "[aura_view_all_doctors]"),
        ],
        menu_type="find_doctor_menu",
        variant="stack",
    )


SPECIALTY_PICKER_OPTIONS: list[tuple[str, str]] = [
    ("General Physician", "General Physician"),
    ("Cardiologist", "Cardiologist"),
    ("Dermatologist", "Dermatologist"),
    ("Neurologist", "Neurologist"),
    ("Orthopedic Surgeon", "Orthopedic Surgeon"),
    ("ENT Specialist", "ENT Specialist"),
    ("Psychiatrist", "Psychiatrist"),
    ("Ophthalmologist", "Ophthalmologist"),
    ("Pediatrician", "Pediatrician"),
    ("Gynecologist", "Gynecologist"),
    ("Pulmonologist", "Pulmonologist"),
    ("Gastroenterologist", "Gastroenterologist"),
]

SPECIALTY_PICKER_LABELS = frozenset(label for label, _ in SPECIALTY_PICKER_OPTIONS)


def build_specialty_picker_ui() -> dict:
    """Specialty list when symptoms are unknown — user can also type any specialty."""
    return build_action_menu_ui(
        SPECIALTY_PICKER_OPTIONS,
        menu_type="specialty_picker",
        variant="stack",
    )


def build_report_upload_menu_ui() -> dict:
    return build_action_menu_ui(
        [
            ("📄 Upload Report", "[aura_upload_report]"),
            ("💊 Upload Prescription", "[aura_upload_prescription]"),
            ("🧪 Upload Lab Report", "[aura_upload_lab]"),
            ("🖼️ Upload Image", "[aura_upload_image]"),
        ],
        menu_type="report_upload_menu",
        variant="stack",
    )


def build_report_followup_ui() -> dict:
    return build_action_menu_ui(
        [
            ("Explain in simple language", "Explain my report in simple language"),
            ("Book appointment", "Book appointment"),
        ],
        menu_type="report_followup",
        variant="stack",
    )


def build_nav_menu_ui() -> dict:
    return build_action_menu_ui(
        [
            ("🏠 Main Menu", "[aura_main_menu]"),
            ("💬 Continue Chat", "Continue chat"),
            ("👨‍⚕️ Find Doctor", "[start_find_doctor]"),
            ("📅 Book Appointment", "Book appointment"),
            ("📄 Upload Report", "[start_explain_report]"),
            ("💊 Prescription Refill", "I'd like a prescription refill"),
            ("📆 Reschedule Appointment", "Reschedule my appointment"),
            ("❌ Cancel Appointment", "Cancel my appointment"),
            ("📹 Start Video Consultation", "Start video consultation"),
            ("📞 Contact Support", "Contact support"),
        ],
        menu_type="nav_menu",
        variant="stack",
    )


def build_booking_offer_ui() -> dict:
    """After symptom assessment — clear Book / Not now actions."""
    return build_post_assessment_ui()
