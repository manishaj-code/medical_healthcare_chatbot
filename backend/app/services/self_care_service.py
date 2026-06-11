"""Symptom-aware self-care guidance after triage."""
from __future__ import annotations

import re

from app.healthcare_policy import patient_first_name
from app.services.symptom_extraction import extract_symptoms_offline, is_non_symptom_message
from app.services.symptom_service import assess_symptoms

_SELF_CARE_PHRASES = (
    "self-care",
    "self care",
    "home care",
    "home remedy",
    "home remedies",
    "what can i do",
    "how can i feel better",
    "tips for my",
    "tell me self-care",
    "self care advice",
    "self-care advice",
    "care tips",
    "relieve my",
    "ease my",
)

_TIP_RULES: list[tuple[tuple[str, ...], list[str]]] = [
    (
        ("fever", "temperature", "chills", "flu"),
        [
            "Drink plenty of water, oral rehydration fluids, or clear soups to stay hydrated.",
            "Rest and sleep as much as your body needs.",
            "Wear light clothing and keep the room comfortably cool.",
            "A lukewarm sponge bath may help if you feel overheated.",
            "Monitor your temperature — seek care if it stays very high or lasts more than 3 days.",
        ],
    ),
    (
        ("headache", "head pain", "migraine"),
        [
            "Rest in a quiet, dim room away from screens and loud noise.",
            "Drink water — dehydration often worsens headaches.",
            "Apply a cool compress to your forehead or the back of your neck.",
            "Eat regular light meals; skipping food can trigger headaches.",
            "Gentle neck stretches may help if tension is contributing.",
        ],
    ),
    (
        ("cough", "sore throat", "throat pain", "phlegm", "cold"),
        [
            "Drink warm water, herbal tea, or broth to soothe your throat.",
            "Honey with warm water may ease a cough (not for children under 1 year).",
            "Avoid smoke, dust, and very cold air.",
            "Use a humidifier or breathe steam to ease congestion.",
            "Gargle with warm salt water for a sore throat.",
        ],
    ),
    (
        ("stomach", "abdominal", "nausea", "vomiting", "diarrhea", "indigestion"),
        [
            "Sip water or oral rehydration fluids frequently in small amounts.",
            "Eat bland, easy-to-digest foods when hungry (rice, toast, banana, applesauce).",
            "Avoid spicy, greasy, or heavy meals until you feel better.",
            "Rest your stomach — eat smaller portions more often.",
            "Seek care if you have severe pain, blood in vomit/stool, or signs of dehydration.",
        ],
    ),
    (
        ("body pain", "muscle", "joint", "back pain", "neck pain", "fatigue", "weakness"),
        [
            "Rest the affected area and avoid heavy lifting or strenuous exercise.",
            "Apply a cold pack for recent pain or swelling; warm compress for stiffness.",
            "Stay hydrated and maintain gentle movement when you feel able.",
            "Ensure you are getting adequate sleep.",
        ],
    ),
    (
        ("rash", "itch", "skin"),
        [
            "Avoid scratching — keep nails short and skin clean.",
            "Wear loose, breathable cotton clothing.",
            "Use fragrance-free moisturizer on dry or irritated skin.",
            "Avoid hot showers and harsh soaps on affected areas.",
        ],
    ),
    (
        ("breathing", "wheez", "shortness of breath"),
        [
            "Sit upright and try slow, steady breathing.",
            "Avoid smoke, strong perfumes, and dusty environments.",
            "Stay well hydrated and rest.",
            "**Seek urgent care** if breathing becomes difficult or lips turn blue.",
        ],
    ),
]


def wants_self_care_advice(text: str) -> bool:
    t = text.strip().lower()
    return any(phrase in t for phrase in _SELF_CARE_PHRASES)


def _symptoms_from_session(session: dict, history: list[dict] | None) -> list[str]:
    symptoms: list[str] = []
    for source in (
        session.get("detected_symptoms"),
        (session.get("triage_collected") or {}).get("symptoms"),
    ):
        if isinstance(source, list):
            for item in source:
                if item and str(item).strip().lower() not in {"unspecified symptoms"}:
                    symptoms.append(str(item).strip())

    if history:
        for msg in history:
            if msg.get("role") not in ("user", "User"):
                continue
            content = (msg.get("content") or "").strip()
            if not content or is_non_symptom_message(content):
                continue
            for label in extract_symptoms_offline(content):
                if label not in symptoms:
                    symptoms.append(label)

    return _dedupe_symptoms(symptoms)[:8]


def _dedupe_symptoms(symptoms: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in symptoms:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(item.strip())
    return unique


def _tips_for_symptoms(symptom_blob: str) -> list[str]:
    tips: list[str] = []
    blob = symptom_blob.lower()
    for keywords, rule_tips in _TIP_RULES:
        if any(kw in blob for kw in keywords):
            tips.extend(rule_tips)
    seen: set[str] = set()
    unique: list[str] = []
    for tip in tips:
        if tip not in seen:
            seen.add(tip)
            unique.append(tip)
    return unique


def build_self_care_reply(
    session: dict,
    history: list[dict] | None,
    patient_name: str = "there",
) -> str:
    pname = patient_first_name(patient_name)

    symptoms = _symptoms_from_session(session, history)
    collected = session.get("triage_collected") or {}
    duration = (collected.get("duration") or "").strip()
    severity = (collected.get("severity") or "").strip()
    conditions = session.get("conditions") or []

    symptom_blob = " ".join(symptoms).lower()
    tips = _tips_for_symptoms(symptom_blob)

    if not tips:
        tips = [
            "Drink plenty of water.",
            "Get enough rest.",
            "Eat light meals when you feel hungry.",
            "Watch your symptoms and note any changes.",
        ]

    assessment = assess_symptoms(symptoms or ["general discomfort"], duration or None, conditions or None)
    risk = assessment["risk_level"]
    risk_val = risk.value if hasattr(risk, "value") else str(risk)

    if symptoms:
        symptom_label = ", ".join(symptoms[:3])
        intro = f"Here are simple things that may help with your **{symptom_label}**:"
    else:
        intro = "Here are simple things you can try at home while you recover:"

    if duration and duration.lower() not in {"not sure", "unspecified", "skip"}:
        intro += f"\n\nYou've mentioned this has been going on for **{duration}**."

    if severity and severity.lower() not in {"not sure", "unspecified", "none reported"}:
        intro += f" You described the severity as **{severity}**."

    body = "\n".join(f"• {tip}" for tip in tips[:7])

    if risk_val in ("high", "emergency"):
        footer = (
            "\n\n⚠️ Your symptoms may need a doctor soon. "
            "Please get medical help, especially if things get worse."
        )
    else:
        footer = (
            "\n\nWatch how you feel over the next day or two. "
            "See a doctor if symptoms get worse, last too long, or you have "
            "trouble breathing, high fever, strong pain, or feel confused."
        )

    closing = (
        "\n\nI can share more tips or help you **book a visit**."
    )

    return f"{intro}\n\n{body}{footer}{closing}"
