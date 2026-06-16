export interface DetectedSymptom {
  label: string;
  icon: string;
}

/** Map any dynamically detected symptom label to a display icon. */
export function iconForSymptom(label: string): string {
  const l = label.toLowerCase();
  if (l.includes("fever") || l.includes("chills")) return "thermostat";
  if (l.includes("cough") || l.includes("throat") || l.includes("breath")) return "air";
  if (l.includes("nausea") || l.includes("vomit")) return "sick";
  if (l.includes("fatigue") || l.includes("tired") || l.includes("weak")) return "battery_alert";
  if (l.includes("rash") || l.includes("skin") || l.includes("itch")) return "dermatology";
  if (l.includes("dizz")) return "rotate_right";
  if (l.includes("eye")) return "visibility";
  if (l.includes("migrain") || l.includes("head")) return "medical_information";
  if (l.includes("chest") || l.includes("heart")) return "cardiology";
  if (l.includes("stomach") || l.includes("abdom") || l.includes("nausea")) return "gastroenterology";
  return "healing";
}

const GENERIC_STANDALONE_SYMPTOMS = new Set([
  "pain",
  "ache",
  "aches",
  "discomfort",
  "hurt",
  "hurting",
  "soreness",
  "sore",
]);

/** Drop generic labels like "pain" when "Leg Pain" is already listed. */
export function collapseRedundantSymptomLabels(labels: string[]): string[] {
  const cleaned = labels.map((raw) => raw.trim()).filter(Boolean);
  if (cleaned.length <= 1) return cleaned;

  const normalized = cleaned.map((label) => label.toLowerCase());
  return cleaned.filter((label, index) => {
    const key = normalized[index];
    if (!GENERIC_STANDALONE_SYMPTOMS.has(key)) return true;
    return !normalized.some(
      (other, otherIndex) =>
        otherIndex !== index && new RegExp(`\\b${key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "i").test(other),
    );
  });
}

/** UI / booking phrases that must never appear as detected symptoms. */
const NON_SYMPTOM_LABELS = new Set([
  "book appointment",
  "book an appointment",
  "tell me self-care advice for my symptoms",
  "tell me more",
  "recommend a doctor",
  "schedule an appointment",
  "find a doctor",
  "find a specialist",
  "show available doctors",
  "self-care tips",
  "in-person consultation",
  "video consultation",
]);

function isNonSymptomLabel(label: string): boolean {
  const key = label.trim().toLowerCase();
  if (!key) return true;
  if (NON_SYMPTOM_LABELS.has(key)) return true;
  return /^(book|schedule)(?:\s+an)?\s+appointment$/.test(key)
    || /^find a (doctor|specialist)$/.test(key)
    || /self[- ]care/.test(key);
}

export function toDetectedSymptoms(labels: string[]): DetectedSymptom[] {
  const seen = new Set<string>();
  const found: DetectedSymptom[] = [];
  for (const raw of collapseRedundantSymptomLabels(labels)) {
    const label = raw.trim();
    if (!label || isNonSymptomLabel(label)) continue;
    const key = label.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    found.push({ label, icon: iconForSymptom(label) });
  }
  return found;
}
