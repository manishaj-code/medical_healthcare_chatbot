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

export function toDetectedSymptoms(labels: string[]): DetectedSymptom[] {
  const seen = new Set<string>();
  const found: DetectedSymptom[] = [];
  for (const raw of labels) {
    const label = raw.trim();
    if (!label) continue;
    const key = label.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    found.push({ label, icon: iconForSymptom(label) });
  }
  return found;
}
