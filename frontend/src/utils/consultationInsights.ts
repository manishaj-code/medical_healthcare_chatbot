import {
  DEFAULT_CLINICAL_RECOMMENDATION,
  formatRiskLevelLabel,
  normalizeRiskLevelKey,
} from "./clinicalSummaryFormat";
import { toDetectedSymptoms, type DetectedSymptom } from "./symptomDetection";

export interface ConsultationStep {
  label: string;
  done: boolean;
}

export interface ConsultationRisk {
  level: string;
  ringLabel: string;
  title: string;
  note: string;
  quote: string;
  variant: "low" | "moderate" | "high";
}

export interface ConsultationInsights {
  percent: number;
  phase: string;
  steps: ConsultationStep[];
  symptoms: DetectedSymptom[];
  risk: ConsultationRisk;
  suggestedSpecialty: string | null;
  hasAssessment: boolean;
}

interface MessageLike {
  role: string;
  content?: string;
  ui?: unknown;
}

function riskVariantForKey(key: ReturnType<typeof normalizeRiskLevelKey>): ConsultationRisk["variant"] {
  if (key === "high" || key === "emergency" || key === "critical") return "high";
  if (key === "medium") return "moderate";
  return "low";
}

function riskFromAssessment(
  emergency: boolean,
  symptomCount: number,
  riskLevel?: string | null,
  recommendationText?: string | null,
  hasAssessment?: boolean,
): ConsultationRisk {
  const riskKey = normalizeRiskLevelKey(riskLevel);
  const riskLabel = formatRiskLevelLabel(riskLevel);
  const quote =
    recommendationText?.trim() ||
    (hasAssessment ? DEFAULT_CLINICAL_RECOMMENDATION : "");

  if (emergency || riskKey === "emergency" || riskKey === "critical") {
    return {
      level: riskKey === "critical" || riskKey === "emergency" ? "Critical" : "High risk",
      ringLabel: riskLabel || "Critical",
      title: "Urgent Attention",
      note: "Seek immediate medical care or emergency services.",
      quote: quote || "Critical indicators detected. Do not delay professional evaluation.",
      variant: "high",
    };
  }

  if (riskKey === "high") {
    return {
      level: "High risk",
      ringLabel: riskLabel || "High",
      title: "Urgent Attention",
      note: "Seek prompt medical evaluation.",
      quote: quote || "Please consult a clinician without delay.",
      variant: "high",
    };
  }

  if (riskKey === "medium") {
    return {
      level: "Medium risk",
      ringLabel: riskLabel || "Medium",
      title: "Monitor Closely",
      note: "Follow up if symptoms persist or worsen.",
      quote: quote || DEFAULT_CLINICAL_RECOMMENDATION,
      variant: "moderate",
    };
  }

  if (riskKey === "low") {
    return {
      level: "Low risk",
      ringLabel: riskLabel || "Low",
      title: "Stable Condition",
      note: "No immediate urgent indicators.",
      quote: quote || DEFAULT_CLINICAL_RECOMMENDATION,
      variant: "low",
    };
  }

  if (hasAssessment) {
    return {
      level: riskLabel ? `${riskLabel} risk` : "Assessed",
      ringLabel: riskLabel || "Assessed",
      title: "Clinical Guidance",
      note: "Based on your reported symptoms.",
      quote: quote || DEFAULT_CLINICAL_RECOMMENDATION,
      variant: riskVariantForKey(riskKey),
    };
  }

  if (symptomCount >= 2) {
    return {
      level: "Medium risk",
      ringLabel: "Medium",
      title: "Monitor Closely",
      note: "Multiple symptoms reported — follow up if symptoms persist.",
      quote: recommendationText?.trim() || DEFAULT_CLINICAL_RECOMMENDATION,
      variant: "moderate",
    };
  }

  return {
    level: "Low risk",
    ringLabel: "Low",
    title: "Stable Condition",
    note: "No immediate urgent indicators.",
    quote: DEFAULT_CLINICAL_RECOMMENDATION,
    variant: "low",
  };
}

export function buildConsultationInsights(
  messages: MessageLike[],
  emergency: boolean,
  symptomLabels: string[],
  riskLevel?: string | null,
  recommendationText?: string | null,
  suggestedSpecialty?: string | null,
): ConsultationInsights {
  const hasAssessment = Boolean(riskLevel || recommendationText || suggestedSpecialty);
  const symptoms = toDetectedSymptoms(symptomLabels);
  const userCount = messages.filter((m) => m.role === "user").length;

  let percent = 30;
  let phase = "Intake Phase";
  if (userCount >= 1) {
    percent = 45;
    phase = "Analysis Phase";
  }
  if (userCount >= 2 || symptoms.length >= 1) {
    percent = 65;
    phase = "Analysis Phase";
  }
  if (userCount >= 3 || symptoms.length >= 2) {
    percent = 80;
    phase = "Correlation Phase";
  }
  if (messages.some((m) => m.ui)) percent = 95;

  const steps: ConsultationStep[] = [
    { label: "History Review", done: true },
    { label: "Initial Inquiry", done: userCount >= 1 },
    { label: "Symptom Correlation", done: userCount >= 2 || symptoms.length > 0 },
  ];

  return {
    percent,
    phase,
    steps,
    symptoms,
    risk: riskFromAssessment(
      emergency,
      symptoms.length,
      riskLevel,
      recommendationText,
      hasAssessment,
    ),
    suggestedSpecialty: suggestedSpecialty?.trim() || null,
    hasAssessment,
  };
}
