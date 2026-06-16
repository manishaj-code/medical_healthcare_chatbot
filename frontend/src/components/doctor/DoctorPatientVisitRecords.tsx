import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import DoctorMedicationTimeline, {
  type MedicationTimelinePayload,
} from "./DoctorMedicationTimeline";
import {
  canStartConsultation,
  consultationModeIcon,
  consultationModeLabel,
  formatDisplayDate,
  formatDoctorTime,
  isOverdueAppointment,
  isUpcomingAppointment,
} from "../../utils/doctorPortal";
import {
  buildClinicalShortDescription,
  formatRiskLevelLabel,
  parsePatientSummaryText,
  riskLevelCssVariant,
  sanitizeClinicalFindingsForDisplay,
} from "../../utils/clinicalSummaryFormat";

export interface VisitAssessment {
  symptoms: string[];
  risk_level: string | null;
  recommended_specialty: string | null;
  recommendation_text: string | null;
  duration: string | null;
}

export interface VisitSoapNote {
  id: string;
  subjective?: string | null;
  objective?: string | null;
  assessment?: string | null;
  plan?: string | null;
  created_at?: string | null;
}

export interface VisitLinkedReport {
  report_id: string;
  filename: string;
  summary?: string;
  abnormal?: { test?: string; value?: string; flag?: string }[];
  created_at?: string | null;
}

export interface VisitPrescriptionItem {
  id: string;
  medicine_name: string;
  strength?: string | null;
  frequency?: string | null;
  duration?: string | null;
  instructions?: string | null;
  source?: string | null;
}

export interface VisitRecord {
  appointment_id: string;
  apt_id: string;
  date: string;
  time: string;
  status: string;
  completed_at?: string | null;
  consultation_mode: string;
  is_video: boolean;
  appointment_reason?: string | null;
  visit_type?: "symptom" | "report_discussion";
  linked_report?: VisitLinkedReport | null;
  chief_complaint?: string | null;
  follow_up_date?: string | null;
  summary?: string | null;
  soap_note?: VisitSoapNote | null;
  assessment?: VisitAssessment | null;
  prescription_items?: VisitPrescriptionItem[];
}

export interface VisitRecordsPayload {
  visits: VisitRecord[];
  medications: { name: string; dosage?: string | null; frequency?: string | null }[];
  medication_timeline?: MedicationTimelinePayload;
  conditions: string[];
  allergies: string[];
  reports: { id: string; created_at?: string | null; analysis: Record<string, unknown> | null }[];
}

function statusLabel(status: string): string {
  const s = status.toLowerCase();
  if (s === "confirmed") return "Confirmed";
  if (s === "completed") return "Completed";
  if (s === "pending") return "Pending";
  if (s === "cancelled") return "Cancelled";
  if (s === "rescheduled") return "Rescheduled";
  return status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
}

function statusTone(status: string): string {
  const s = status.toLowerCase();
  if (s === "completed" || s === "confirmed") return "success";
  if (s === "cancelled") return "cancelled";
  if (s === "pending") return "warning";
  return "info";
}

function visitIcon(visit: VisitRecord): string {
  if (visit.visit_type === "report_discussion") return "lab_profile";
  if (visit.is_video) return "videocam";
  if (visit.status === "completed") return "task_alt";
  if (visit.status === "cancelled") return "event_busy";
  return "calendar_month";
}

interface VisitConsultFor {
  isReport: boolean;
  text: string;
  chips: string[];
}

function resolveVisitConsultFor(visit: VisitRecord): VisitConsultFor | null {
  if (visit.visit_type === "report_discussion" || visit.linked_report || visit.appointment_reason) {
    const reason =
      visit.appointment_reason?.trim() ||
      (visit.linked_report?.filename
        ? `Medical Report Review — ${visit.linked_report.filename}`
        : "Medical Report Review & Consultation");
    return { isReport: true, text: reason, chips: [] };
  }

  const symptoms = visit.assessment?.symptoms ?? [];
  if (symptoms.length > 0) {
    return { isReport: false, text: "", chips: symptoms };
  }

  const complaint = visit.chief_complaint?.trim() || visit.soap_note?.subjective?.trim();
  if (complaint) {
    const chips = complaint
      .split(/,\s*/)
      .map((part) => part.trim())
      .filter(Boolean);
    return { isReport: false, text: "", chips: chips.length > 0 ? chips : [complaint] };
  }

  return null;
}

function VisitConsultForRow({
  consultFor,
  compact = false,
}: {
  consultFor: VisitConsultFor;
  compact?: boolean;
}) {
  const chips = consultFor.isReport ? [consultFor.text] : consultFor.chips;
  if (chips.length === 0) return null;

  return (
    <div className={`dp-visit-consult-for${compact ? " dp-visit-consult-for--compact" : ""}`}>
      <span className="dp-visit-consult-for-label">Consult for:</span>
      <div className="dp-visit-preview-chips">
        {chips.slice(0, compact ? 3 : chips.length).map((chip) => (
          <span
            key={chip}
            className={`dp-visit-preview-chip${
              consultFor.isReport ? " dp-visit-preview-chip--report" : ""
            }`}
          >
            {chip}
          </span>
        ))}
        {compact && chips.length > 3 && (
          <span className="dp-visit-preview-chip dp-visit-preview-chip--more">+{chips.length - 3}</span>
        )}
      </div>
    </div>
  );
}

function aiSummaryLines(summary: string, hasTriageBlock: boolean): string[] {
  const parsed = parsePatientSummaryText(summary);
  if (!hasTriageBlock) {
    const fields = {
      chiefComplaint: (parsed.chiefComplaint as string | null) ?? null,
      symptomLabels: (parsed.chiefComplaint as string)
        ? String(parsed.chiefComplaint).split(/,\s*/)
        : [],
      duration: (parsed.duration as string | null) ?? null,
      riskLevel: (parsed.riskLevel as string | null) ?? null,
      recommendedSpecialty: (parsed.recommendedSpecialty as string | null) ?? null,
      medicalHistory: (parsed.medicalHistory as string[]) ?? [],
      medications: (parsed.medications as string[]) ?? [],
      allergies: (parsed.allergies as string[]) ?? [],
      recommendation: (parsed.recommendation as string | null) ?? null,
    };
    const built = buildClinicalShortDescription(fields);
    if (built && built.length > 0) return built;
  }

  const lines: string[] = [];
  if (parsed.recommendation) lines.push(String(parsed.recommendation));
  const history = (parsed.medicalHistory as string[]) ?? [];
  const meds = (parsed.medications as string[]) ?? [];
  const allergies = (parsed.allergies as string[]) ?? [];
  if (history.length) lines.push(`Medical history: ${history.join(", ")}.`);
  if (meds.length) lines.push(`Medications: ${meds.join(", ")}.`);
  if (allergies.length) lines.push(`Allergies: ${allergies.join(", ")}.`);
  if (!lines.length) {
    const cleaned = summary
      .replace(/^PATIENT SUMMARY \(Pre-Consultation\)\s*/i, "")
      .replace(/\s+/g, " ")
      .trim();
    if (cleaned) {
      return cleaned
        .split(/(?<=[.!?])\s+/)
        .map((s) => s.trim())
        .filter(Boolean)
        .slice(0, 5);
    }
  }
  return lines;
}

const CONSULTATION_NOTE_FIELDS = [
  {
    key: "subjective" as const,
    label: "Chief complaint",
    icon: "record_voice_over",
    variant: "complaint" as const,
  },
  {
    key: "assessment" as const,
    label: "Diagnosis",
    icon: "diagnosis",
    variant: "diagnosis" as const,
  },
  {
    key: "objective" as const,
    label: "Clinical findings",
    icon: "stethoscope",
    variant: "findings" as const,
  },
  {
    key: "plan" as const,
    label: "Treatment plan",
    icon: "assignment",
    variant: "plan" as const,
  },
] as const;

const FINDING_LABEL_RE =
  /(Presenting symptoms|Duration|Medical history|Current medications|Known allergies):\s*/gi;

interface StructuredFindings {
  symptoms: string[];
  duration: string | null;
  history: string[];
  medications: string[];
  allergies: string[];
  notes: string[];
}

function listFromFieldValue(value: string): string[] {
  return value
    .replace(/\.\s*$/, "")
    .split(/,\s*/)
    .map((part) => part.trim())
    .filter(Boolean);
}

function extractDurationValue(raw: string): { duration: string; extra: string } {
  const value = raw.trim();
  if (!value) return { duration: "", extra: "" };

  const rangeMatch = value.match(/^([\w\d\s\-–]+(?:day|days|week|weeks|hour|hours|month|months))\.?\s*/i);
  if (rangeMatch) {
    return {
      duration: rangeMatch[1].trim(),
      extra: value.slice(rangeMatch[0].length).trim(),
    };
  }

  const firstSentence = value.match(/^([^.!?]+[.!?])\s*/);
  if (
    firstSentence &&
    firstSentence[1].length <= 42 &&
    /day|week|hour|month|year/i.test(firstSentence[1]) &&
    !/patient|rest |see a doctor|recommended/i.test(firstSentence[1])
  ) {
    return {
      duration: firstSentence[1].replace(/\.\s*$/, "").trim(),
      extra: value.slice(firstSentence[0].length).trim(),
    };
  }

  if (value.length <= 32 && !/patient|rest |see a doctor/i.test(value)) {
    return { duration: value.replace(/\.\s*$/, "").trim(), extra: "" };
  }

  return { duration: "", extra: value };
}

function splitNarrative(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  const sentences = splitSentences(trimmed);
  return sentences.length > 0 ? sentences : [trimmed];
}

function parseClinicalFindingsStructured(text: string): StructuredFindings {
  const result: StructuredFindings = {
    symptoms: [],
    duration: null,
    history: [],
    medications: [],
    allergies: [],
    notes: [],
  };

  const matches = [...text.matchAll(FINDING_LABEL_RE)];
  if (!matches.length) {
    result.notes = splitNarrative(text);
    return result;
  }

  const firstIndex = matches[0].index ?? 0;
  if (firstIndex > 0) {
    const lead = text.slice(0, firstIndex).trim();
    if (lead) result.notes.push(...splitNarrative(lead));
  }

  for (let i = 0; i < matches.length; i += 1) {
    const match = matches[i];
    const label = match[1].toLowerCase();
    const valueStart = (match.index ?? 0) + match[0].length;
    const valueEnd = i + 1 < matches.length ? (matches[i + 1].index ?? text.length) : text.length;
    const value = text.slice(valueStart, valueEnd).trim();
    if (!value) continue;

    if (label === "presenting symptoms") {
      result.symptoms = listFromFieldValue(value);
    } else if (label === "duration") {
      const { duration, extra } = extractDurationValue(value);
      if (duration) result.duration = duration;
      if (extra) result.notes.push(...splitNarrative(extra));
    } else if (label === "medical history") {
      result.history = listFromFieldValue(value);
    } else if (label === "current medications") {
      result.medications = listFromFieldValue(value);
    } else if (label === "known allergies") {
      result.allergies = listFromFieldValue(value);
    }
  }

  return result;
}

function ClinicalFindingsDisplay({ text }: { text: string }) {
  const data = parseClinicalFindingsStructured(text);
  const hasStructured =
    data.symptoms.length > 0 ||
    Boolean(data.duration) ||
    data.history.length > 0 ||
    data.medications.length > 0 ||
    data.allergies.length > 0;

  if (!hasStructured) {
    const lines = text.includes("\n")
      ? text.split(/\n+/).map((line) => line.trim()).filter(Boolean)
      : splitNarrative(text);
    return (
      <ul className="dp-visit-clinical-bullets">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    );
  }

  return (
    <div className="dp-visit-findings-layout">
      {data.symptoms.length > 0 && (
        <div className="dp-visit-findings-section">
          <span className="dp-visit-findings-label">Symptoms</span>
          <div className="dp-visit-chips">
            {data.symptoms.map((symptom) => (
              <span key={symptom} className="dp-visit-chip">
                {symptom}
              </span>
            ))}
          </div>
        </div>
      )}

      {(data.duration || data.history.length > 0 || data.medications.length > 0 || data.allergies.length > 0) && (
        <div className="dp-visit-findings-meta">
          {data.duration && (
            <span className="dp-visit-meta-pill">
              <span className="material-symbols-outlined">schedule</span>
              {data.duration}
            </span>
          )}
          {data.history.map((item) => (
            <span key={`history-${item}`} className="dp-visit-meta-pill">
              <span className="material-symbols-outlined">history</span>
              {item}
            </span>
          ))}
          {data.medications.map((item) => (
            <span key={`med-${item}`} className="dp-visit-meta-pill">
              <span className="material-symbols-outlined">medication</span>
              {item}
            </span>
          ))}
          {data.allergies.map((item) => (
            <span key={`allergy-${item}`} className="dp-visit-meta-pill dp-visit-meta-pill--alert">
              <span className="material-symbols-outlined">warning</span>
              {item}
            </span>
          ))}
        </div>
      )}

      {data.notes.length > 0 && (
        <div className="dp-visit-findings-notes">
          <span className="dp-visit-findings-label">Clinical notes</span>
          <ul className="dp-visit-clinical-bullets">
            {data.notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function splitSentences(text: string): string[] {
  return text
    .split(/(?<=[.!?])\s+/)
    .map((part) => part.trim())
    .filter((part) => part.length > 12);
}

function clinicalTextContent(text: string, variant: "complaint" | "diagnosis" | "findings" | "plan"): ReactNode {
  const trimmed = text.trim();
  if (!trimmed) return null;

  const lines = trimmed
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);

  const numbered =
    lines.length > 1 && lines.every((line) => /^\d+[\.)]\s+/.test(line));

  if (numbered || variant === "plan") {
    const planLines = numbered
      ? lines
      : lines.length > 1
        ? lines
        : splitSentences(trimmed);
    const listItems = planLines.map((line) => line.replace(/^\d+[\.)]\s+/, "").trim()).filter(Boolean);
    if (listItems.length > 1) {
      return (
        <ol className="dp-visit-clinical-list">
          {listItems.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ol>
      );
    }
  }

  if (variant === "findings") {
    return <ClinicalFindingsDisplay text={trimmed} />;
  }

  if (variant === "complaint") {
    return <p className="dp-visit-clinical-complaint">{trimmed}</p>;
  }

  if (variant === "diagnosis") {
    return <p className="dp-visit-clinical-diagnosis">{trimmed}</p>;
  }

  return <p className="dp-visit-clinical-text">{trimmed}</p>;
}

function VisitConsultationRecord({
  soap,
  isCompleted,
  assessment,
}: {
  soap: VisitSoapNote;
  isCompleted: boolean;
  assessment?: VisitAssessment | null;
}) {
  const displaySoap: VisitSoapNote = { ...soap };
  if (isCompleted && soap.objective) {
    const cleaned = sanitizeClinicalFindingsForDisplay(soap.objective, assessment);
    displaySoap.objective = cleaned || null;
  }

  const fields = CONSULTATION_NOTE_FIELDS.filter((field) => {
    const value = displaySoap[field.key];
    return typeof value === "string" && value.trim().length > 0;
  });

  if (!fields.length) return null;

  const planText = displaySoap.plan ?? "";
  const planLines = planText
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  const planIsDifferential =
    planLines.length > 0 && planLines.every((line) => /^\d+[\.)]\s+Consider\b/i.test(line));

  return (
    <section className="dp-visit-block dp-visit-block--primary">
      <div className="dp-visit-block-head">
        <span className="material-symbols-outlined">clinical_notes</span>
        <h4>{isCompleted ? "Consultation record" : "Draft consultation notes"}</h4>
      </div>
      <div className="dp-visit-clinical-stack">
        {fields.map((field) => (
          <section
            key={field.key}
            className={`dp-visit-clinical-block dp-visit-clinical-block--${field.variant}`}
          >
            <h5>
              <span className="material-symbols-outlined">{field.icon}</span>
              {field.variant === "plan" && planIsDifferential ? "Differential considerations" : field.label}
            </h5>
            {clinicalTextContent(displaySoap[field.key] ?? "", field.variant)}
            {field.variant === "plan" && planIsDifferential && (
              <p className="dp-visit-clinical-hint">Working diagnoses considered during the visit.</p>
            )}
          </section>
        ))}
      </div>
    </section>
  );
}

function VisitAiSummary({ summary, hasTriageBlock }: { summary: string; hasTriageBlock: boolean }) {
  const lines = aiSummaryLines(summary, hasTriageBlock);
  if (!lines.length) return null;
  return (
    <section className="dp-visit-block dp-visit-block--ai">
      <div className="dp-visit-block-head">
        <span className="material-symbols-outlined filled-icon">auto_awesome</span>
        <h4>AI pre-consult summary</h4>
      </div>
      <ul className="dp-visit-summary-list">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </section>
  );
}

function AsidePanel({
  icon,
  title,
  count,
  emptyIcon,
  emptyText,
  children,
  variant,
}: {
  icon: string;
  title: string;
  count?: number;
  emptyIcon: string;
  emptyText: string;
  children: ReactNode;
  variant?: "alert";
}) {
  const isEmpty = !children;
  return (
    <div className={`dp-visit-aside-card${variant === "alert" ? " dp-visit-aside-card--alert" : ""}`}>
      <div className="dp-visit-section-head">
        <span className="material-symbols-outlined">{icon}</span>
        <h3>{title}</h3>
        {count != null && count > 0 && <span className="dp-visit-section-count">{count}</span>}
      </div>
      {isEmpty ? (
        <div className="dp-visit-aside-empty">
          <div className="dp-visit-aside-empty-icon" aria-hidden>
            <span className="material-symbols-outlined">{emptyIcon}</span>
          </div>
          <p>{emptyText}</p>
        </div>
      ) : (
        <div className="dp-visit-aside-body">{children}</div>
      )}
    </div>
  );
}

function VisitPrescriptionBlock({ items }: { items: VisitPrescriptionItem[] }) {
  if (items.length === 0) return null;
  return (
    <section className="dp-visit-block dp-visit-block--rx">
      <div className="dp-visit-block-head">
        <span className="material-symbols-outlined">medication</span>
        <h4>Prescribed this visit</h4>
      </div>
      <ul className="dp-visit-rx-list">
        {items.map((item) => (
          <li key={item.id}>
            <strong>{item.medicine_name}</strong>
            <span>
              {[item.strength, item.frequency, item.duration].filter(Boolean).join(" · ")}
            </span>
            {item.instructions ? <p className="dp-visit-note">{item.instructions}</p> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

function VisitCard({
  visit,
  defaultOpen,
  highlight,
  onMarkCompleted,
  onMarkCancelled,
}: {
  visit: VisitRecord;
  defaultOpen?: boolean;
  highlight?: boolean;
  onMarkCompleted?: (appointmentId: string) => Promise<void>;
  onMarkCancelled?: (appointmentId: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(defaultOpen ?? false);
  const [busy, setBusy] = useState(false);
  const overdue = isOverdueAppointment(visit.date, visit.time, visit.status);
  const canConduct = canStartConsultation(visit.date, visit.status);
  const isCompleted = visit.status.toLowerCase() === "completed";
  const risk = visit.assessment?.risk_level;
  const symptoms = visit.assessment?.symptoms ?? [];
  const consultFor = resolveVisitConsultFor(visit);
  const prescriptionItems = visit.prescription_items ?? [];
  const hasSoap = Boolean(visit.soap_note);
  const hasAiSummary = Boolean(visit.summary && !/no (ai )?summary yet/i.test(visit.summary));
  const showAiSummary = hasAiSummary && !hasSoap;
  const hasDetails =
    symptoms.length > 0 || showAiSummary || hasSoap || prescriptionItems.length > 0;

  return (
    <article
      id={`visit-${visit.appointment_id}`}
      className={`dp-visit-card dp-visit-card--${visit.status}${open ? " dp-visit-card--open" : ""}${
        visit.is_video ? " dp-visit-card--video" : ""
      }${overdue ? " dp-visit-card--overdue" : ""}${highlight ? " dp-visit-card--highlight" : ""}`}
    >
      <button
        type="button"
        className="dp-visit-card-head"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <div className={`dp-visit-card-icon dp-visit-card-icon--${statusTone(visit.status)}`}>
          <span className="material-symbols-outlined">{visitIcon(visit)}</span>
        </div>

        <div className="dp-visit-card-main">
          <div className="dp-visit-card-topline">
            <strong>{formatDisplayDate(visit.date)}</strong>
            <span className="dp-visit-time">{formatDoctorTime(visit.time)}</span>
            <span className={`dp-visit-status dp-visit-status--${overdue ? "warning" : statusTone(visit.status)}`}>
              {overdue ? "Past due" : statusLabel(visit.status)}
            </span>
          </div>
          <div className="dp-visit-card-sub">
            <span className="dp-visit-apt">{visit.apt_id}</span>
            {visit.consultation_mode && (
              <span className="dp-visit-mode">
                <span className="material-symbols-outlined">
                  {consultationModeIcon(visit.consultation_mode, visit.is_video)}
                </span>
                {consultationModeLabel(visit.consultation_mode, visit.is_video)} consult
              </span>
            )}
          </div>
          {!open && consultFor && <VisitConsultForRow consultFor={consultFor} compact />}
          {!open && prescriptionItems.length > 0 && (
            <div className="dp-visit-rx-preview">
              <span className="material-symbols-outlined">medication</span>
              {prescriptionItems.length} medication{prescriptionItems.length !== 1 ? "s" : ""} prescribed
            </div>
          )}
        </div>

        <span className={`material-symbols-outlined dp-visit-chevron${open ? " dp-visit-chevron--open" : ""}`}>
          expand_more
        </span>
      </button>

      {canConduct && (
        <div className="dp-visit-card-actions">
          <Link
            to={`/doctor/consultation/${visit.appointment_id}`}
            className="dp-btn dp-btn--primary dp-btn--sm"
            onClick={(e) => e.stopPropagation()}
          >
            <span className="material-symbols-outlined">stethoscope</span>
            Start consultation
          </Link>
        </div>
      )}

      {open && (
        <div className="dp-visit-card-body">
          {consultFor && <VisitConsultForRow consultFor={consultFor} />}

          {consultFor?.isReport && visit.linked_report && (
            <section className="dp-visit-block dp-visit-block--report">
              <div className="dp-visit-block-head">
                <span className="material-symbols-outlined">description</span>
                <h4>Linked report</h4>
              </div>
              <p className="dp-visit-report-name">
                <strong>{visit.linked_report.filename}</strong>
              </p>
              {visit.linked_report.summary ? (
                <p className="dp-visit-note">{visit.linked_report.summary}</p>
              ) : null}
            </section>
          )}

          {!hasDetails && visit.status !== "completed" && (
            <div className="dp-visit-pending-note">
              <span className="material-symbols-outlined">info</span>
              <p>
                Triage summary and clinical notes will appear here after the patient completes
                pre-visit assessment or after you document the consultation.
              </p>
            </div>
          )}

          {symptoms.length > 0 && (!hasSoap || isCompleted) && (
            <section className="dp-visit-block">
              <div className="dp-visit-block-head">
                <span className="material-symbols-outlined">healing</span>
                <h4>{hasSoap && isCompleted ? "Pre-visit triage" : "Symptoms & triage"}</h4>
              </div>
              <div className="dp-visit-chips">
                {symptoms.map((s) => (
                  <span key={s} className="dp-visit-chip">
                    {s}
                  </span>
                ))}
              </div>
              <div className="dp-visit-meta-row">
                {visit.assessment?.duration && (
                  <span className="dp-visit-meta-pill">
                    <span className="material-symbols-outlined">schedule</span>
                    {visit.assessment.duration}
                  </span>
                )}
                {risk && (
                  <span className={`dp-clinical-risk-badge dp-clinical-risk-badge--${riskLevelCssVariant(risk)}`}>
                    {formatRiskLevelLabel(risk)}
                  </span>
                )}
                {visit.assessment?.recommended_specialty && (
                  <span className="dp-visit-meta-pill">
                    <span className="material-symbols-outlined">medical_services</span>
                    {visit.assessment.recommended_specialty}
                  </span>
                )}
              </div>
              {visit.assessment?.recommendation_text && (
                <p className="dp-visit-note">{visit.assessment.recommendation_text}</p>
              )}
            </section>
          )}

          {showAiSummary && (
            <VisitAiSummary summary={visit.summary!} hasTriageBlock={symptoms.length > 0} />
          )}

          {visit.soap_note && (
            <VisitConsultationRecord
              soap={visit.soap_note}
              isCompleted={isCompleted}
              assessment={visit.assessment}
            />
          )}

          <VisitPrescriptionBlock items={prescriptionItems} />

          {visit.status === "completed" && !visit.soap_note && !visit.summary && symptoms.length === 0 && prescriptionItems.length === 0 && (
            <p className="dp-visit-empty-detail">No structured notes captured for this visit yet.</p>
          )}

          {visit.follow_up_date && (
            <div className="dp-visit-followup">
              <span className="material-symbols-outlined">event</span>
              <span>
                Follow-up scheduled for <strong>{formatDisplayDate(visit.follow_up_date)}</strong>
              </span>
            </div>
          )}

          {visit.completed_at && (
            <p className="dp-visit-completed-at">
              <span className="material-symbols-outlined">check_circle</span>
              Completed {new Date(visit.completed_at).toLocaleString()}
            </p>
          )}

          {overdue && onMarkCompleted && onMarkCancelled && (
            <div className="dp-visit-status-actions">
              <p>This visit time has passed. Update the status after the consult or if the patient did not attend.</p>
              <div className="dp-visit-status-actions-btns">
                <button
                  type="button"
                  className="dp-btn dp-btn--primary dp-btn--sm"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await onMarkCompleted(visit.appointment_id);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  {busy ? "Saving…" : "Mark completed"}
                </button>
                <button
                  type="button"
                  className="dp-btn dp-btn--ghost dp-btn--sm"
                  disabled={busy}
                  onClick={async () => {
                    setBusy(true);
                    try {
                      await onMarkCancelled(visit.appointment_id);
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Mark cancelled
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export default function DoctorPatientVisitRecords({
  data,
  onMarkCompleted,
  onMarkCancelled,
  onOpenRefills,
}: {
  data: VisitRecordsPayload;
  onMarkCompleted?: (appointmentId: string) => Promise<void>;
  onMarkCancelled?: (appointmentId: string) => Promise<void>;
  onOpenRefills?: () => void;
}) {
  const [highlightVisitId, setHighlightVisitId] = useState<string | null>(null);

  const scrollToVisit = (appointmentId: string) => {
    const el = document.getElementById(`visit-${appointmentId}`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    setHighlightVisitId(appointmentId);
    window.setTimeout(() => setHighlightVisitId(null), 2400);
  };

  const visitCardProps = (visit: VisitRecord, defaultOpen?: boolean) => ({
    visit,
    defaultOpen,
    highlight: highlightVisitId === visit.appointment_id,
    onMarkCompleted,
    onMarkCancelled,
  });

  const normStatus = (status: string) => status.toLowerCase();
  const completed = data.visits.filter((v) => normStatus(v.status) === "completed");
  const cancelled = data.visits.filter((v) => {
    const s = normStatus(v.status);
    return s === "cancelled" || s === "canceled";
  });
  const completedIds = new Set(completed.map((v) => v.appointment_id));
  const cancelledIds = new Set(cancelled.map((v) => v.appointment_id));
  const overdue = data.visits.filter(
    (v) =>
      !completedIds.has(v.appointment_id) &&
      !cancelledIds.has(v.appointment_id) &&
      isOverdueAppointment(v.date, v.time, v.status),
  );
  const upcoming = data.visits.filter(
    (v) =>
      !completedIds.has(v.appointment_id) &&
      !cancelledIds.has(v.appointment_id) &&
      isUpcomingAppointment(v.date, v.time, v.status),
  );

  return (
    <div className="dp-visit-records">
      <div className="dp-visit-stats">
        <div className="dp-visit-stat">
          <span className="dp-visit-stat-value">{data.visits.length}</span>
          <span className="dp-visit-stat-label">Total visits</span>
        </div>
        <div className={`dp-visit-stat${completed.length ? " dp-visit-stat--success" : ""}`}>
          <span className="dp-visit-stat-value">{completed.length}</span>
          <span className="dp-visit-stat-label">Completed</span>
        </div>
        <div className={`dp-visit-stat${upcoming.length ? " dp-visit-stat--active" : ""}`}>
          <span className="dp-visit-stat-value">{upcoming.length}</span>
          <span className="dp-visit-stat-label">Upcoming</span>
        </div>
        <div className={`dp-visit-stat${overdue.length ? " dp-visit-stat--warning" : ""}`}>
          <span className="dp-visit-stat-value">{overdue.length}</span>
          <span className="dp-visit-stat-label">Past due</span>
        </div>
        <div className="dp-visit-stat">
          <span className="dp-visit-stat-value">{data.reports.length}</span>
          <span className="dp-visit-stat-label">Lab reports</span>
        </div>
      </div>

      <div className="dp-visit-records-grid">
        <div className="dp-visit-records-main">
          {overdue.length > 0 && (
            <section className="dp-visit-group-card dp-visit-group-card--overdue">
              <header className="dp-visit-section-head">
                <span className="material-symbols-outlined">schedule</span>
                <h3>Needs attention</h3>
                <span className="dp-visit-section-count">{overdue.length}</span>
              </header>
              <div className="dp-visit-group-body">
                <div className="dp-visit-timeline">
                  {overdue.map((visit) => (
                    <VisitCard key={visit.appointment_id} {...visitCardProps(visit)} />
                  ))}
                </div>
              </div>
            </section>
          )}

          {upcoming.length > 0 && (
            <section className="dp-visit-group-card">
              <header className="dp-visit-section-head">
                <span className="material-symbols-outlined">event_upcoming</span>
                <h3>Upcoming visits</h3>
                <span className="dp-visit-section-count">{upcoming.length}</span>
              </header>
              <div className="dp-visit-group-body">
                <div className="dp-visit-timeline">
                  {upcoming.map((visit) => (
                    <VisitCard key={visit.appointment_id} {...visitCardProps(visit)} />
                  ))}
                </div>
              </div>
            </section>
          )}

          {completed.length > 0 && (
            <section className="dp-visit-group-card">
              <header className="dp-visit-section-head">
                <span className="material-symbols-outlined">history</span>
                <h3>Completed visits</h3>
                <span className="dp-visit-section-count">{completed.length}</span>
              </header>
              <div className="dp-visit-group-body">
                <div className="dp-visit-timeline">
                  {completed.map((visit) => (
                    <VisitCard key={visit.appointment_id} {...visitCardProps(visit)} />
                  ))}
                </div>
              </div>
            </section>
          )}

          {cancelled.length > 0 && (
            <section className="dp-visit-group-card dp-visit-group-card--muted">
              <header className="dp-visit-section-head">
                <span className="material-symbols-outlined">block</span>
                <h3>Cancelled</h3>
                <span className="dp-visit-section-count">{cancelled.length}</span>
              </header>
              <div className="dp-visit-group-body">
                <div className="dp-visit-timeline">
                  {cancelled.map((visit) => (
                    <VisitCard key={visit.appointment_id} {...visitCardProps(visit)} />
                  ))}
                </div>
              </div>
            </section>
          )}

          {data.visits.length === 0 && (
            <div className="dp-visit-empty-main">
              <span className="material-symbols-outlined">event_busy</span>
              <strong>No consultation records yet</strong>
              <p>Appointments and visit summaries will appear here after the patient books with you.</p>
            </div>
          )}
        </div>

        <aside className="dp-visit-records-aside">
          <AsidePanel
            icon="medication"
            title="Medication plan"
            count={data.medication_timeline?.summary.active_count ?? data.medications.length}
            emptyIcon="medication"
            emptyText="No prescriptions linked to visits yet."
          >
            {data.medication_timeline ? (
              <DoctorMedicationTimeline
                timeline={data.medication_timeline}
                onViewVisit={scrollToVisit}
                onOpenRefills={onOpenRefills}
              />
            ) : data.medications.length > 0 ? (
              <ul className="dp-visit-med-list">
                {data.medications.map((m) => (
                  <li key={m.name}>
                    <span className="dp-visit-med-icon material-symbols-outlined">medication</span>
                    <div>
                      <strong>{m.name}</strong>
                      <span>{[m.dosage, m.frequency].filter(Boolean).join(" · ") || "Active prescription"}</span>
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}
          </AsidePanel>

          <AsidePanel
            icon="history"
            title="Medical history"
            count={data.conditions.length}
            emptyIcon="diagnosis"
            emptyText="No conditions recorded in the patient profile."
          >
            {data.conditions.length > 0 ? (
              <ul className="dp-visit-tag-list">
                {data.conditions.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            ) : null}
          </AsidePanel>

          <AsidePanel
            icon="warning"
            title="Allergies"
            count={data.allergies.length}
            emptyIcon="warning"
            emptyText="No known allergies documented."
            variant={data.allergies.length > 0 ? "alert" : undefined}
          >
            {data.allergies.length > 0 ? (
              <ul className="dp-visit-tag-list dp-visit-tag-list--alert">
                {data.allergies.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            ) : null}
          </AsidePanel>

          <AsidePanel
            icon="science"
            title="Lab reports"
            count={data.reports.length}
            emptyIcon="science"
            emptyText="No lab reports uploaded by this patient."
          >
            {data.reports.length > 0 ? (
              <ul className="dp-visit-report-list">
                {data.reports.map((r) => (
                  <li key={r.id}>
                    <span className="material-symbols-outlined">description</span>
                    <div>
                      <strong>Report {r.id.slice(0, 8).toUpperCase()}</strong>
                      {r.created_at && (
                        <span>{new Date(r.created_at).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                        })}</span>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}
          </AsidePanel>
        </aside>
      </div>
    </div>
  );
}
