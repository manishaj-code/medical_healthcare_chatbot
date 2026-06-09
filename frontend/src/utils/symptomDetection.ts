export interface DetectedSymptom {
  label: string;
  icon: string;
}

const SYMPTOM_PATTERNS: { pattern: RegExp; label: string; icon: string }[] = [
  { pattern: /\bmigrain\w*\b/i, label: "Migraine", icon: "medical_information" },
  { pattern: /\bheadache\b/i, label: "Headache", icon: "medical_information" },
  { pattern: /\bfever\b/i, label: "Fever", icon: "thermostat" },
  { pattern: /\bcough\b/i, label: "Cough", icon: "air" },
  { pattern: /\bnausea\b/i, label: "Nausea", icon: "sick" },
  { pattern: /\bfatigue\b/i, label: "Fatigue", icon: "battery_alert" },
  { pattern: /\bpain\b/i, label: "Pain", icon: "healing" },
  { pattern: /\bdizz(y|iness)\b/i, label: "Dizziness", icon: "rotate_right" },
  { pattern: /\brash\b/i, label: "Rash", icon: "dermatology" },
  { pattern: /\bsore throat\b/i, label: "Sore throat", icon: "air" },
  { pattern: /\beye\b/i, label: "Eye pressure", icon: "visibility" },
];

const NON_SYMPTOM_USER_RE =
  /^(less than 1 day|1-3 days|4-7 days|over 1 week|yes|no|no other symptoms|\[start_symptom_triage\]|mild|moderate|severe)/i;

const REPORT_OR_ACTION_RE =
  /please (analyze|summarize|explain)|health risk assessment|medical report|uploaded report|out-of-range|abnormal values|book an appointment|find a (doctor|specialist)/i;

const SKIP_USER_MESSAGES = new Set([
  "yes",
  "no",
  "ok",
  "okay",
  "thanks",
  "thank you",
  "i'd like to book an appointment with a doctor.",
]);

function titleCaseSymptom(text: string): string {
  return text
    .split(/\s+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

export function iconForSymptom(label: string): string {
  const l = label.toLowerCase();
  if (l.includes("fever")) return "thermostat";
  if (l.includes("cough") || l.includes("throat")) return "air";
  if (l.includes("nausea")) return "sick";
  if (l.includes("fatigue")) return "battery_alert";
  if (l.includes("rash")) return "dermatology";
  if (l.includes("dizz")) return "rotate_right";
  if (l.includes("eye")) return "visibility";
  if (l.includes("migrain") || l.includes("head")) return "medical_information";
  return "healing";
}

export function isNonSymptomUserMessage(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) return true;
  if (SKIP_USER_MESSAGES.has(trimmed.toLowerCase())) return true;
  if (NON_SYMPTOM_USER_RE.test(trimmed)) return true;
  if (REPORT_OR_ACTION_RE.test(trimmed)) return true;
  if (trimmed.length > 80) return true;
  return false;
}

export function extractSymptomLabelsFromMessage(content: string): string[] {
  const text = content.trim();
  if (!text || isNonSymptomUserMessage(text)) return [];

  const fromPatterns: string[] = [];
  for (const item of SYMPTOM_PATTERNS) {
    if (item.pattern.test(text)) fromPatterns.push(item.label);
  }
  if (fromPatterns.length) return fromPatterns;

  const haveMatch = text.match(
    /(?:i have|i'?ve had|i am having|feeling|suffering from|experiencing)\s+(?:a\s+)?(.+)/i
  );
  if (haveMatch) {
    const phrase = haveMatch[1].replace(/[.!?]+$/, "").trim();
    if (phrase && !isNonSymptomUserMessage(phrase)) {
      if (/\bmigrain\w*\b/i.test(phrase)) return ["Migraine"];
      return [titleCaseSymptom(phrase)];
    }
  }

  if (/\bmigrain\w*\b/i.test(text)) return ["Migraine"];

  if (text.split(/\s+/).length <= 5 && !/\d/.test(text)) {
    return [titleCaseSymptom(text)];
  }

  return [];
}

export function detectSymptomsFromMessages(
  messages: { role: string; content: string }[]
): DetectedSymptom[] {
  const seen = new Set<string>();
  const found: DetectedSymptom[] = [];
  for (const msg of messages) {
    if (msg.role !== "user" && String(msg.role).toLowerCase() !== "user") continue;
    for (const label of extractSymptomLabelsFromMessage(msg.content)) {
      const key = label.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      found.push({ label, icon: iconForSymptom(label) });
    }
  }
  return found;
}

export function detectSymptomStringsFromMessages(
  messages: { role: string; content: string }[]
): string[] {
  return detectSymptomsFromMessages(messages).map((s) => s.label);
}
