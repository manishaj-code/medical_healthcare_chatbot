"""Structured UI payloads for interactive chat (doctor/slot pickers)."""


def build_doctor_list_ui(result: dict) -> dict | None:
    doctors = result.get("doctors", [])
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
                "slots": [
                    {
                        "label": s["label"],
                        "doctor_id": s.get("doctor_id", d["id"]),
                        "doctor_name": s.get("doctor_name", d["name"]),
                        "slot_date": s.get("slot_date"),
                        "slot_time": s.get("slot_time"),
                        "message": f"{d['name']} {s['label']}",
                    }
                    for s in d.get("slots", [])[:6]
                ],
            }
            for d in doctors
        ],
    }


def build_slot_list_ui(doctor_name: str, doctor_id: str, slots: list[dict]) -> dict | None:
    if not slots:
        return None
    return {
        "type": "slot_list",
        "doctor_id": doctor_id,
        "doctor_name": doctor_name,
        "slots": [
            {
                "label": s["label"],
                "doctor_id": s.get("doctor_id", doctor_id),
                "doctor_name": s.get("doctor_name", doctor_name),
                "slot_date": s.get("slot_date"),
                "slot_time": s.get("slot_time"),
                "message": s["label"],
            }
            for s in slots[:8]
        ],
    }


def doctor_list_intro(count: int) -> str:
    return f"I found **{count} doctors** with open appointments."


def slot_list_intro(doctor_name: str) -> str:
    return f"Pick a time with **{doctor_name}**."


def build_appointment_confirmed_ui(result: dict) -> dict | None:
    if not result.get("appointment_id"):
        return None
    return {
        "type": "appointment_confirmed",
        "appointment_id": result["appointment_id"],
        "apt_id": result.get("apt_id", ""),
        "doctor_name": result.get("doctor_name", "Doctor"),
        "label": result.get("label", ""),
    }


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


def build_symptom_picker_ui() -> dict:
    return {
        "type": "symptom_picker",
        "options": _choice_options([
            ("Headache", "Headache"),
            ("Fever", "Fever"),
            ("Cough", "Cough"),
            ("Body pain", "Body pain"),
            ("Nausea", "Nausea"),
            ("Sore throat", "Sore throat"),
            ("Fatigue", "Fatigue"),
            ("Rash", "Rash"),
        ]),
    }


def build_duration_picker_ui() -> dict:
    return {
        "type": "duration_picker",
        "options": _choice_options([
            ("Less than 1 day", "Less than 1 day"),
            ("1–3 days", "1-3 days"),
            ("4–7 days", "4-7 days"),
            ("Over 1 week", "Over 1 week"),
        ]),
    }


def build_severity_picker_ui() -> dict:
    return {
        "type": "severity_picker",
        "options": _choice_options([
            ("Mild (1–3)", "Mild, about 2 out of 10"),
            ("Moderate (4–6)", "Moderate, about 5 out of 10"),
            ("Severe (7–10)", "Severe, about 8 out of 10"),
            ("Getting worse", "Symptoms are getting worse"),
        ]),
    }


def build_booking_offer_ui() -> dict:
    return build_yes_no_ui(
        yes_label="Yes, show doctors",
        yes_message="Yes",
        no_label="No thanks",
        no_message="No",
    )
