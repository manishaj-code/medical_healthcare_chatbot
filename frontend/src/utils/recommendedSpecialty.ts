import { api } from "../api/client";
import { fetchConversations } from "./chatConversations";
import { detectSymptomStringsFromMessages, isNonSymptomUserMessage } from "./symptomDetection";

export interface HistoryRecommendation {
  specialty: string;
  bookableSpecialty: string;
  recommendation?: string;
  symptoms: string[];
  source: "assessment" | "chat" | "cache";
}

const BOOKABLE_SPECIALTIES = [
  "General Physician",
  "Cardiologist",
  "Neurologist",
  "Dermatologist",
  "Pediatrician",
];

const SPECIALTY_ALIASES: Record<string, string> = {
  "general physician": "General Physician",
  cardiologist: "Cardiologist",
  neurologist: "Neurologist",
  dermatologist: "Dermatologist",
  pediatrician: "Pediatrician",
  gastroenterologist: "Gastroenterologist",
  emergency: "Emergency",
};

const CACHE_KEY = "mediai_history_recommendation";

interface AssessmentRow {
  specialty?: string | null;
  speciality?: string | null;
  recommendation?: string | null;
  symptoms?: string[];
  completed_at?: string | null;
}

interface ChatMessage {
  role: string;
  content: string;
}

function normalizeSpecialty(raw: string): string | null {
  const cleaned = raw.replace(/\*\*/g, "").trim();
  if (!cleaned) return null;
  const key = cleaned.toLowerCase();
  if (SPECIALTY_ALIASES[key]) return SPECIALTY_ALIASES[key];
  const match = BOOKABLE_SPECIALTIES.find((s) => s.toLowerCase() === key);
  if (match) return match;
  if (key.includes("cardio")) return "Cardiologist";
  if (key.includes("neuro")) return "Neurologist";
  if (key.includes("derma") || key.includes("skin")) return "Dermatologist";
  if (key.includes("pediatr") || key.includes("child")) return "Pediatrician";
  if (key.includes("gastro")) return "Gastroenterologist";
  if (key.includes("emergency")) return "Emergency";
  if (key.includes("general") || key.includes("physician")) return "General Physician";
  return cleaned;
}

export function toBookableSpecialty(specialty: string): string {
  if (BOOKABLE_SPECIALTIES.includes(specialty)) return specialty;
  if (specialty === "Emergency" || specialty === "Gastroenterologist") return "General Physician";
  return "General Physician";
}

export function parseSpecialtyFromText(text: string): string | null {
  const patterns = [
    /recommend(?:\s+seeing)?\s+a\s+\*\*([^*]+)\*\*/i,
    /recommend(?:\s+seeing)?\s+a\s+([A-Za-z][A-Za-z\s]+?)(?:[.!,]|(?:\s+for)|(?:\s+—)|$)/i,
    /I'd recommend(?:\s+seeing)?\s+a\s+\*\*([^*]+)\*\*/i,
    /specialist:\s*\*\*([^*]+)\*\*/i,
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match?.[1]) {
      const normalized = normalizeSpecialty(match[1]);
      if (normalized) return normalized;
    }
  }
  return null;
}

function normalizeSymptomList(symptoms: string[] | undefined | null): string[] {
  if (!symptoms?.length) return [];
  const seen = new Set<string>();
  const cleaned: string[] = [];
  for (const raw of symptoms) {
    const text = raw.trim();
    if (!text || isNonSymptomUserMessage(text)) continue;
    const key = text.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    cleaned.push(text);
  }
  return cleaned.slice(-4);
}

function readCache(): HistoryRecommendation | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as HistoryRecommendation;
    if (!parsed?.specialty || !normalizeSymptomList(parsed.symptoms).length) return null;
    return { ...parsed, symptoms: normalizeSymptomList(parsed.symptoms), source: "cache" };
  } catch {
    return null;
  }
}

export function clearStaleRecommendationCache(): void {
  if (!readCache() && localStorage.getItem(CACHE_KEY)) {
    localStorage.removeItem(CACHE_KEY);
  }
}

export function saveHistoryRecommendation(rec: Omit<HistoryRecommendation, "source" | "bookableSpecialty">) {
  const symptoms = normalizeSymptomList(rec.symptoms);
  if (!symptoms.length) return;
  const payload: HistoryRecommendation = {
    ...rec,
    symptoms,
    bookableSpecialty: toBookableSpecialty(rec.specialty),
    source: "cache",
  };
  localStorage.setItem(CACHE_KEY, JSON.stringify(payload));
}

async function fromAssessments(): Promise<HistoryRecommendation | null> {
  const rows = await api<AssessmentRow[]>("/api/v1/symptoms/assessments");
  const latest = rows.find((r) => r.specialty || r.speciality);
  if (!latest) return null;
  const symptoms = normalizeSymptomList(latest.symptoms);
  if (!symptoms.length) return null;
  const specialty = normalizeSpecialty(latest.specialty || latest.speciality || "") || "General Physician";
  return {
    specialty,
    bookableSpecialty: toBookableSpecialty(specialty),
    recommendation: latest.recommendation || undefined,
    symptoms,
    source: "assessment",
  };
}

async function fromChatMessages(): Promise<HistoryRecommendation | null> {
  const conversations = await fetchConversations();
  if (!conversations.length) return null;

  for (const conv of conversations) {
    const messages = await api<ChatMessage[]>(`/api/v1/chat/conversations/${conv.id}/messages`);
    const symptoms = detectSymptomStringsFromMessages(messages);
    if (!symptoms.length) continue;

    let specialty = inferSpecialtyFromSymptoms(symptoms);
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i];
      if (msg.role !== "assistant") continue;
      const parsed = parseSpecialtyFromText(msg.content);
      if (parsed) {
        specialty = parsed;
        break;
      }
    }

    return {
      specialty,
      bookableSpecialty: toBookableSpecialty(specialty),
      symptoms,
      source: "chat",
    };
  }
  return null;
}

export async function resolveRecommendedFromHistory(): Promise<HistoryRecommendation | null> {
  try {
    const fromDb = await fromAssessments();
    if (fromDb) {
      saveHistoryRecommendation(fromDb);
      return fromDb;
    }
  } catch {
    /* fall through */
  }

  try {
    const fromChat = await fromChatMessages();
    if (fromChat) {
      saveHistoryRecommendation(fromChat);
      return fromChat;
    }
  } catch {
    /* fall through */
  }

  return readCache();
}

export function inferSpecialtyFromSymptoms(symptoms: string[]): string {
  const blob = symptoms.join(" ").toLowerCase();
  if (blob.includes("chest") && (blob.includes("pain") || blob.includes("discomfort"))) return "Cardiologist";
  if (/\brash\b|\bskin\b|\bitch\b/.test(blob)) return "Dermatologist";
  if (/\bchild\b|\binfant\b|\bbaby\b/.test(blob)) return "Pediatrician";
  if (/\bseizure\b|\bnumb\b|\bmigraine\b/.test(blob)) return "Neurologist";
  return "General Physician";
}

export function buildBannerCopy(rec: HistoryRecommendation | null, specialty: string): string {
  const symptoms = normalizeSymptomList(rec?.symptoms);
  if (!symptoms.length) return "";
  const symptomText = symptoms.join(", ").toLowerCase();
  return `Based on your reported symptoms of ${symptomText}, our AI system suggests scheduling with a ${specialty} for further evaluation.`;
}
