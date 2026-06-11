import { collapseRedundantSymptomLabels } from "./symptomDetection";

export const DEFAULT_CLINICAL_RECOMMENDATION = "Physician evaluation advised.";

export type RiskLevelKey = "low" | "medium" | "high" | "emergency" | "critical";

/** Canonical risk key from API or summary text (`moderate` → `medium`). */
export function normalizeRiskLevelKey(riskLevel?: string | null): RiskLevelKey | null {
  if (!riskLevel) return null;
  const v = riskLevel.trim().toLowerCase();
  if (v === "moderate" || v === "medium") return "medium";
  if (v === "low") return "low";
  if (v === "high") return "high";
  if (v === "emergency") return "emergency";
  if (v === "critical") return "critical";
  return null;
}

/** Shared display label for doctor dashboard and patient portal (`medium` → `Medium`). */
export function formatRiskLevelLabel(riskLevel?: string | null): string | null {
  const key = normalizeRiskLevelKey(riskLevel);
  if (!key) {
    const trimmed = riskLevel?.trim();
    return trimmed && !isEmptyClinicalValue(trimmed) ? trimmed : null;
  }
  const labels: Record<RiskLevelKey, string> = {
    low: "Low",
    medium: "Medium",
    high: "High",
    emergency: "Emergency",
    critical: "Critical",
  };
  return labels[key];
}

export function riskLevelCssVariant(riskLevel?: string | null): "low" | "moderate" | "high" | "neutral" {
  const key = normalizeRiskLevelKey(riskLevel);
  if (key === "high" || key === "emergency" || key === "critical") return "high";
  if (key === "medium") return "moderate";
  if (key === "low") return "low";
  return "neutral";
}

export interface ClinicalSummaryFields {
  chiefComplaint: string | null;
  symptomLabels: string[];
  duration: string | null;
  riskLevel: string | null;
  recommendedSpecialty: string | null;
  medicalHistory: string[];
  medications: string[];
  allergies: string[];
  recommendation: string | null;
}

const SUMMARY_FIELD_LABELS: { key: keyof ClinicalSummaryFields; label: string; isList?: boolean }[] = [
  { key: "chiefComplaint", label: "Chief Complaint" },
  { key: "duration", label: "Duration" },
  { key: "riskLevel", label: "Risk Level" },
  { key: "recommendedSpecialty", label: "Recommended Specialty" },
  { key: "medicalHistory", label: "Medical History", isList: true },
  { key: "medications", label: "Medications", isList: true },
  { key: "allergies", label: "Allergies", isList: true },
];

export function isEmptyClinicalValue(value: string | null | string[] | undefined): boolean {
  if (value === null || value === undefined) return true;
  if (Array.isArray(value)) return value.length === 0;
  const trimmed = value.trim().toLowerCase();
  return !trimmed || trimmed === "n/a" || trimmed === "none" || trimmed === "not recorded";
}

function sanitizeListItems(items: string[]): string[] {
  return items
    .map((s) => s.replace(/\s*Recommendation:.*$/i, "").trim())
    .filter((s) => s && !isEmptyClinicalValue(s));
}

function parseListValue(raw: string): string[] {
  if (isEmptyClinicalValue(raw)) return [];
  return sanitizeListItems(raw.split(",").map((s) => s.trim()).filter(Boolean));
}

export function complaintSymptoms(complaint: string | null): string[] {
  if (!complaint || isEmptyClinicalValue(complaint)) return [];
  return complaint.split(",").map((s) => s.trim()).filter(Boolean);
}

/** Brief bullet lines for doctor quick review (excludes clinical recommendation). */
export function buildClinicalShortDescription(fields: ClinicalSummaryFields): string[] | null {
  const symptoms =
    fields.symptomLabels.length > 0
      ? fields.symptomLabels
      : complaintSymptoms(fields.chiefComplaint);

  if (symptoms.length === 0) return null;

  const lines: string[] = [];
  const complaintText = symptoms.join(", ");
  const durationPart = !isEmptyClinicalValue(fields.duration) ? ` for ${fields.duration!.trim()}` : "";
  lines.push(`Patient reports ${complaintText}${durationPart}.`);

  const risk = formatRiskLevelLabel(fields.riskLevel);
  const specialty = fields.recommendedSpecialty?.trim();
  if (risk || !isEmptyClinicalValue(specialty)) {
    const triageParts: string[] = [];
    if (risk) triageParts.push(`${risk} risk`);
    if (!isEmptyClinicalValue(specialty)) triageParts.push(`${specialty} follow-up suggested`);
    lines.push(`Triage: ${triageParts.join(". ")}.`);
  }

  const hasHistory = fields.medicalHistory.length > 0;
  const hasMeds = fields.medications.length > 0;
  const hasAllergies = fields.allergies.length > 0;

  if (!hasHistory && !hasMeds && !hasAllergies) {
    lines.push(
      "No significant medical history, current medications, or known drug allergies on record.",
    );
  } else {
    lines.push(
      hasHistory
        ? `Medical history: ${fields.medicalHistory.join(", ")}.`
        : "Medical history: None recorded.",
    );
    lines.push(
      hasMeds
        ? `Medications: ${fields.medications.join(", ")}.`
        : "Medications: None recorded.",
    );
    lines.push(
      hasAllergies
        ? `Allergies: ${fields.allergies.join(", ")}.`
        : "Allergies: No known drug allergies.",
    );
  }

  return lines;
}

/** Merge symptom labels from chat, assessments, history, and stored summary text. */
export function resolveSymptomLabels(sources: {
  detectedSymptoms?: string[];
  assessmentSymptoms?: string[];
  historySymptoms?: string[];
  chiefComplaintText?: string | null;
}): string[] {
  const seen = new Set<string>();
  const out: string[] = [];

  const add = (raw: string) => {
    const label = raw.trim();
    const key = label.toLowerCase();
    if (!label || isEmptyClinicalValue(label) || seen.has(key)) return;
    seen.add(key);
    out.push(label);
  };

  for (const s of sources.detectedSymptoms ?? []) add(s);
  for (const s of sources.assessmentSymptoms ?? []) add(s);
  for (const s of sources.historySymptoms ?? []) add(s);
  for (const s of complaintSymptoms(sources.chiefComplaintText ?? null)) add(s);

  return collapseRedundantSymptomLabels(out);
}

export function parsePatientSummaryText(text: string): Partial<ClinicalSummaryFields> {
  const result: Partial<ClinicalSummaryFields> = {};
  if (!text || /no (ai )?summary yet/i.test(text)) return result;

  const body = text.replace(/^PATIENT SUMMARY \(Pre-Consultation\)\s*/i, "").trim();
  if (!body) return result;

  let mainBody = body;
  const recMatch = body.match(/Recommendation:\s*([\s\S]*)$/i);
  if (recMatch) {
    const rec = recMatch[1].trim();
    result.recommendation = isEmptyClinicalValue(rec) ? null : rec;
    mainBody = body.slice(0, recMatch.index).trim();
  }

  for (let i = 0; i < SUMMARY_FIELD_LABELS.length; i++) {
    const { key, label, isList } = SUMMARY_FIELD_LABELS[i];
    const nextLabels = SUMMARY_FIELD_LABELS.slice(i + 1).map((f) => f.label);
    const nextPattern =
      nextLabels.length > 0
        ? `(?=(?:${nextLabels.map((l) => l.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")}):)`
        : "$";
    const re = new RegExp(`${label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}:\\s*([\\s\\S]*?)${nextPattern}`, "i");
    const match = mainBody.match(re);
    if (!match) continue;

    const raw = match[1].trim();
    if (isList) {
      result[key] = parseListValue(raw);
    } else {
      result[key] = isEmptyClinicalValue(raw) ? null : raw;
    }
  }

  return result;
}

export type ConsultClinicalSource = {
  detected_symptoms: string[];
  assessments: { symptoms: string[] }[];
  consultation_history?: { detected_symptoms: string[] }[];
  duration: string | null;
  risk_level: string | null;
  recommended_specialty: string | null;
  recommendation_text: string | null;
  conditions: string[];
  medications: { name: string }[];
  allergies: string[];
};

function withSymptomLabels(
  fields: Omit<ClinicalSummaryFields, "symptomLabels">,
  sources: Parameters<typeof resolveSymptomLabels>[0],
): ClinicalSummaryFields {
  const symptomLabels = resolveSymptomLabels(sources);
  return {
    ...fields,
    symptomLabels,
    chiefComplaint: symptomLabels.length > 0 ? symptomLabels.join(", ") : fields.chiefComplaint,
  };
}

export function buildClinicalFieldsFromConsult(consult: ConsultClinicalSource): ClinicalSummaryFields {
  const assessmentSymptoms = consult.assessments.flatMap((a) => a.symptoms ?? []);
  const historySymptoms = (consult.consultation_history ?? []).flatMap((c) => c.detected_symptoms ?? []);
  const symptomLabels = resolveSymptomLabels({
    detectedSymptoms: consult.detected_symptoms,
    assessmentSymptoms,
    historySymptoms,
  });

  return withSymptomLabels(
    {
      chiefComplaint: symptomLabels.length > 0 ? symptomLabels.join(", ") : null,
      duration: consult.duration,
      riskLevel: consult.risk_level,
      recommendedSpecialty: consult.recommended_specialty,
      medicalHistory: consult.conditions,
      medications: consult.medications.map((m) => m.name),
      allergies: consult.allergies,
      recommendation: consult.recommendation_text,
    },
    {
      detectedSymptoms: consult.detected_symptoms,
      assessmentSymptoms,
      historySymptoms,
    },
  );
}

export function mergeClinicalFields(
  primary: ClinicalSummaryFields,
  fallback: Partial<ClinicalSummaryFields>,
): ClinicalSummaryFields {
  const fallbackHistory = sanitizeListItems(fallback.medicalHistory ?? []);
  const fallbackMeds = sanitizeListItems(fallback.medications ?? []);
  const fallbackAllergies = sanitizeListItems(fallback.allergies ?? []);

  const merged: Omit<ClinicalSummaryFields, "symptomLabels"> = {
    chiefComplaint: primary.chiefComplaint ?? fallback.chiefComplaint ?? null,
    duration: primary.duration ?? fallback.duration ?? null,
    riskLevel: primary.riskLevel ?? fallback.riskLevel ?? null,
    recommendedSpecialty: primary.recommendedSpecialty ?? fallback.recommendedSpecialty ?? null,
    medicalHistory: primary.medicalHistory.length > 0 ? primary.medicalHistory : fallbackHistory,
    medications: primary.medications.length > 0 ? primary.medications : fallbackMeds,
    allergies: primary.allergies.length > 0 ? primary.allergies : fallbackAllergies,
    recommendation: primary.recommendation ?? fallback.recommendation ?? null,
  };

  return withSymptomLabels(merged, {
    detectedSymptoms: [...primary.symptomLabels, ...complaintSymptoms(fallback.chiefComplaint ?? null)],
    chiefComplaintText: merged.chiefComplaint ?? fallback.chiefComplaint ?? null,
  });
}

export function buildMergedClinicalFields(
  summaryText: string,
  consult?: ConsultClinicalSource | null,
): ClinicalSummaryFields {
  const parsed = parsePatientSummaryText(summaryText);
  const parsedFields: ClinicalSummaryFields = {
    chiefComplaint: (parsed.chiefComplaint as string | null) ?? null,
    symptomLabels: complaintSymptoms((parsed.chiefComplaint as string | null) ?? null),
    duration: (parsed.duration as string | null) ?? null,
    riskLevel: (parsed.riskLevel as string | null) ?? null,
    recommendedSpecialty: (parsed.recommendedSpecialty as string | null) ?? null,
    medicalHistory: sanitizeListItems((parsed.medicalHistory as string[]) ?? []),
    medications: sanitizeListItems((parsed.medications as string[]) ?? []),
    allergies: sanitizeListItems((parsed.allergies as string[]) ?? []),
    recommendation: (parsed.recommendation as string | null) ?? null,
  };

  if (!consult) return parsedFields;

  const fromConsult = buildClinicalFieldsFromConsult(consult);
  const merged = mergeClinicalFields(fromConsult, parsedFields);

  const symptomLabels = resolveSymptomLabels({
    detectedSymptoms: consult.detected_symptoms,
    assessmentSymptoms: consult.assessments.flatMap((a) => a.symptoms ?? []),
    historySymptoms: (consult.consultation_history ?? []).flatMap((c) => c.detected_symptoms ?? []),
    chiefComplaintText: merged.chiefComplaint ?? parsedFields.chiefComplaint,
  });

  return {
    ...merged,
    symptomLabels,
    chiefComplaint: symptomLabels.length > 0 ? symptomLabels.join(", ") : null,
  };
}

export function clinicalFieldsFromSummaryText(text: string): ClinicalSummaryFields {
  return buildMergedClinicalFields(text, null);
}

export function isStructuredClinicalSummaryText(text: string): boolean {
  if (!text || /no (ai )?summary yet/i.test(text) || /loading clinical summary/i.test(text)) {
    return false;
  }
  return /PATIENT SUMMARY|Chief Complaint:/i.test(text);
}
