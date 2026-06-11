from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SymptomAssessment
from app.models.enums import RiskLevel

# ── Symptom routing rules ─────────────────────────────────────────────────────
# Each entry: (keywords_any, specialty, risk, recommendation_text)
# Rules are checked in order; first match wins for specialty/risk.
# Risk may be upgraded if conditions flag is set.
_SYMPTOM_RULES = [
    # Emergency — always checked first
    (["chest pain", "heart attack", "can't breathe", "cannot breathe", "severe bleeding",
      "loss of consciousness", "unconscious", "stroke", "paralysis", "seizure"],
     "Emergency", RiskLevel.emergency,
     "Seek emergency care immediately. Call 911 or go to the nearest ER."),

    # Mental health crisis
    (["suicidal", "self-harm", "want to die", "end my life"],
     "Psychiatrist", RiskLevel.emergency,
     "Please seek immediate mental health support. Call a crisis line or go to the ER."),

    # Cardiology
    (["palpitation", "irregular heartbeat", "heart flutter", "racing heart",
      "shortness of breath", "breathing difficulty", "edema", "swollen legs", "swollen ankles"],
     "Cardiologist", RiskLevel.high,
     "Cardiac symptoms need prompt evaluation. Please see a cardiologist or go to urgent care."),

    # Neurology
    (["severe headache", "migraine", "vision changes", "double vision", "blurred vision",
      "dizziness", "vertigo", "memory loss", "confusion", "numbness", "tingling", "tremor",
      "weakness in limb", "balance problem"],
     "Neurologist", RiskLevel.medium,
     "Neurological symptoms may need specialist evaluation. Rest and hydrate; seek care if symptoms worsen."),

    # Respiratory
    (["cough", "shortness of breath", "wheezing", "breathlessness", "sore throat",
      "hoarseness", "phlegm", "mucus"],
     "Pulmonologist", RiskLevel.medium,
     "Respiratory symptoms should be monitored. Stay hydrated, rest, and avoid irritants. See a doctor if symptoms persist beyond 5 days or worsen."),

    # Gastroenterology
    (["stomach pain", "abdominal pain", "abdominal cramp", "nausea", "vomiting", "diarrhea",
      "constipation", "bloating", "indigestion", "acid reflux", "heartburn", "bloody stool",
      "rectal bleeding", "loss of appetite"],
     "Gastroenterologist", RiskLevel.medium,
     "Gastrointestinal symptoms may need investigation. Eat light meals, stay hydrated, and avoid spicy food. Seek care if severe or persistent."),

    # Dermatology
    (["rash", "skin rash", "itching", "hives", "eczema", "psoriasis", "acne", "skin lesion",
      "skin discolouration", "skin discoloration", "blisters", "peeling skin"],
     "Dermatologist", RiskLevel.low,
     "Avoid scratching or touching the affected area. Keep it clean and dry. A dermatologist can provide targeted treatment."),

    # Orthopedics / Musculoskeletal
    (["joint pain", "knee pain", "back pain", "neck pain", "shoulder pain", "hip pain",
      "muscle pain", "muscle cramp", "sprain", "fracture", "bone pain", "arthritis",
      "swollen joint", "stiff joints"],
     "Orthopedist", RiskLevel.medium,
     "Rest the affected area and apply ice for swelling. Avoid strenuous activity. An orthopedist can assess if imaging or physiotherapy is needed."),

    # ENT
    (["ear pain", "earache", "ear infection", "hearing loss", "tinnitus", "nasal congestion",
      "runny nose", "sinusitis", "sinus pain", "nosebleed"],
     "ENT Specialist", RiskLevel.low,
     "Stay hydrated and use saline rinse for nasal symptoms. Seek care if symptoms persist beyond a week or you develop high fever."),

    # Ophthalmology
    (["eye pain", "eye redness", "conjunctivitis", "eye discharge", "blurred vision",
      "vision loss", "eye irritation", "dry eyes"],
     "Ophthalmologist", RiskLevel.medium,
     "Avoid rubbing your eyes. Rinse with clean water if irritated. See an ophthalmologist promptly for any vision changes."),

    # Urology / Nephrology
    (["urinary pain", "painful urination", "burning urination", "frequent urination",
      "blood in urine", "kidney pain", "flank pain", "urinary infection", "uti"],
     "Urologist", RiskLevel.medium,
     "Drink plenty of water. Urinary symptoms often respond well to treatment — see a doctor if you have fever or severe pain."),

    # Endocrinology
    (["diabetes", "blood sugar", "thyroid", "weight gain", "weight loss", "excessive thirst",
      "frequent urination", "fatigue", "hair loss", "cold intolerance", "heat intolerance"],
     "Endocrinologist", RiskLevel.medium,
     "Metabolic symptoms need proper evaluation. Monitor your diet and fluid intake, and see a specialist for blood tests."),

    # Pediatrics
    (["child", "infant", "baby", "toddler", "newborn"],
     "Pediatrician", RiskLevel.medium,
     "Children's symptoms need careful monitoring. Consult a pediatrician for proper age-appropriate assessment."),

    # Gynaecology
    (["menstrual", "period pain", "irregular period", "vaginal discharge", "pelvic pain",
      "pregnancy", "breast pain", "breast lump"],
     "Gynaecologist", RiskLevel.medium,
     "These symptoms should be evaluated by a gynaecologist for proper diagnosis and treatment."),

    # Psychiatry / Mental Health
    (["anxiety", "depression", "panic attack", "stress", "insomnia", "sleep problem",
      "mood swing", "hallucination", "phobia", "eating disorder"],
     "Psychiatrist", RiskLevel.medium,
     "Mental health symptoms are important to address. Consider talking to a mental health professional for support and guidance."),

    # Headache / general pain (lower priority than neurology above)
    (["headache", "migraine", "head pain"],
     "General Physician", RiskLevel.low,
     "Rest in a quiet, dark room and stay hydrated. Take over-the-counter pain relief if needed. See a doctor if severe, sudden, or recurring."),

    # Fever / Infection (general — lower priority than combinations above)
    (["fever", "high temperature", "chills", "sweating", "flu", "cold", "infection", "weakness", "fatigue"],
     "General Physician", RiskLevel.medium,
     "Rest and stay well hydrated. Monitor your temperature. Seek care if fever is above 39.5°C (103°F) or lasts more than 3 days."),
]


def assess_symptoms(
    symptoms: list[str],
    duration: str | None,
    conditions: list[str] | None,
) -> dict:
    """
    Dynamic rule-based symptom assessment.
    Returns risk_level, recommended_specialty, recommendation_text.
    Uses the LLM triage result when available (via tool_assess_symptoms_llm);
    this function is the offline/fallback path.
    """
    risk = RiskLevel.low
    specialty = "General Physician"
    recommendation = (
        "Monitor your symptoms and stay hydrated. "
        "Consult a doctor if symptoms worsen or persist beyond a few days."
    )

    symptom_blob = " ".join(s.lower() for s in (symptoms or []))
    has_chronic = bool(conditions)

    # Check rules in priority order
    for keywords, sp, rl, rec in _SYMPTOM_RULES:
        if any(kw in symptom_blob for kw in keywords):
            specialty = sp
            risk = rl
            recommendation = rec
            break

    # Upgrade risk for patients with chronic conditions
    if has_chronic and risk == RiskLevel.low:
        risk = RiskLevel.medium
        recommendation = (
            f"Given your medical history, these symptoms should be monitored closely. "
            f"Consult a {specialty} within 24–48 hours if they do not improve."
        )
    elif has_chronic and risk == RiskLevel.medium:
        recommendation = (
            f"Given your medical history, please consult a {specialty} promptly. "
            "Your existing conditions may influence how these symptoms should be managed."
        )

    # Upgrade risk for long duration
    if duration and risk in (RiskLevel.low, RiskLevel.medium):
        long_duration = any(w in duration.lower() for w in ("week", "month", "weeks", "months", "long", "while"))
        if long_duration and risk == RiskLevel.low:
            risk = RiskLevel.medium
            recommendation = (
                f"Symptoms lasting this long should be evaluated by a {specialty}. "
                "Schedule an appointment soon."
            )

    return {
        "risk_level": risk,
        "recommended_specialty": specialty,
        "recommendation_text": recommendation,
    }


async def save_assessment(
    db: AsyncSession,
    patient_id: UUID,
    symptoms: list[str],
    duration: str | None = None,
    conditions: list[str] | None = None,
    conversation_id: UUID | None = None,
) -> SymptomAssessment:
    result = assess_symptoms(symptoms, duration, conditions)
    assessment = SymptomAssessment(
        patient_id=patient_id,
        conversation_id=conversation_id,
        symptoms_json={"symptoms": symptoms, "conditions": conditions or []},
        duration=duration,
        risk_level=result["risk_level"],
        recommended_specialty=result["recommended_specialty"],
        recommendation_text=result["recommendation_text"],
        completed_at=datetime.now(timezone.utc),
    )
    db.add(assessment)
    await db.flush()
    return assessment
