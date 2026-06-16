import { buildConsultationInsights } from "../../utils/consultationInsights";
import { buildMergedClinicalFields, isEmptyClinicalValue } from "../../utils/clinicalSummaryFormat";
import { toDetectedSymptoms } from "../../utils/symptomDetection";
import ClinicalSummaryPanel from "./ClinicalSummaryPanel";
import DoctorPatientCareOverview from "./DoctorPatientCareOverview";

export interface PatientConsultOverview {
  rollup: {
    completed_visits: number;
    reports_count: number;
    upcoming_visits: number;
    chief_complaints: string[];
    diagnoses: string[];
    treatment_plans: string[];
    report_summaries: string[];
    latest_follow_up: string | null;
  };
  timeline: {
    type: "visit_completed" | "visit_upcoming" | "report_uploaded";
    title: string;
    subtitle?: string | null;
    apt_id?: string;
    appointment_id?: string;
    date?: string;
    time?: string;
    status?: string;
    consultation_mode?: string;
    appointment_reason?: string | null;
    chief_complaint?: string | null;
    diagnosis?: string | null;
    treatment_plan?: string | null;
    clinical_findings_excerpt?: string | null;
    follow_up_date?: string | null;
    linked_report?: {
      report_id: string;
      filename: string;
      summary?: string;
      abnormal?: { test?: string; value?: string; flag?: string }[];
    } | null;
    report?: {
      report_id: string;
      filename: string;
      summary?: string;
      abnormal?: { test?: string; value?: string; flag?: string }[];
      created_at?: string | null;
    };
  }[];
  narrative: string;
}

export interface ConsultationSummaryData {
  detected_symptoms: string[];
  risk_level: string | null;
  recommended_specialty: string | null;
  recommendation_text: string | null;
  duration: string | null;
  emergency_flag: boolean;
  conversation_count: number;
  total_messages: number;
  assessments: {
    id: string;
    symptoms: string[];
    risk_level: string | null;
    recommended_specialty: string | null;
    recommendation_text: string | null;
    completed_at: string | null;
  }[];
  consultation_history: {
    conversation_id: string;
    title: string;
    created_at: string | null;
    message_count: number;
    emergency_flag: boolean;
    detected_symptoms: string[];
    preview: string;
  }[];
  conditions: string[];
  medications: { name: string; dosage: string | null; frequency: string | null }[];
  allergies: string[];
  memory_facts: string[];
  patient_consult_overview?: PatientConsultOverview | null;
}

interface Props {
  aiSummary: string;
  consult: ConsultationSummaryData;
  latestMessages: { role: string; content: string; ui?: unknown }[];
  onOpenChats: () => void;
}

function formatWhen(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export default function DoctorPatientConsultSummary({
  aiSummary,
  consult,
  latestMessages,
  onOpenChats,
}: Props) {
  const clinicalFields = buildMergedClinicalFields(aiSummary, consult);
  const displaySymptoms = toDetectedSymptoms(clinicalFields.symptomLabels);
  const insights = buildConsultationInsights(
    latestMessages,
    consult.emergency_flag,
    clinicalFields.symptomLabels,
    clinicalFields.riskLevel,
    isEmptyClinicalValue(clinicalFields.recommendation) ? null : clinicalFields.recommendation,
    clinicalFields.recommendedSpecialty,
  );

  return (
    <div className="dp-patient-consult-overview">
      {consult.patient_consult_overview && (
        <DoctorPatientCareOverview overview={consult.patient_consult_overview} />
      )}

      <div className="dp-glass dp-glass--clinical-summary">
        <ClinicalSummaryPanel
          summaryText={aiSummary}
          fields={clinicalFields}
          consult={consult}
          variant="full"
        />
      </div>

      <div className="dp-consult-insights-grid">
        <div className="dp-glass dp-consult-progress-card">
          <h3 className="dp-consult-card-title">Consultation Progress</h3>
          <div className="dp-consult-progress-head">
            <span className="dp-consult-phase">{insights.phase}</span>
            <span className="dp-consult-percent">{insights.percent}%</span>
          </div>
          <div className="dp-consult-progress-bar">
            <div className="dp-consult-progress-fill" style={{ width: `${insights.percent}%` }} />
          </div>
          <ul className="dp-consult-steps">
            {insights.steps.map((step) => (
              <li key={step.label} className={step.done ? "dp-consult-step--done" : ""}>
                <span className="material-symbols-outlined filled-icon">
                  {step.done ? "check_circle" : "radio_button_unchecked"}
                </span>
                {step.label}
              </li>
            ))}
          </ul>
          <p className="dp-muted-note">
            {consult.conversation_count} session{consult.conversation_count !== 1 ? "s" : ""} ·{" "}
            {consult.total_messages} messages
          </p>
        </div>

        <div className="dp-glass">
          <h3 className="dp-consult-card-title">Detected Symptoms</h3>
          {displaySymptoms.length === 0 ? (
            <p className="dp-muted-note" style={{ margin: 0 }}>
              No symptoms detected from chatbot consultations yet.
            </p>
          ) : (
            <div className="dp-consult-symptom-tags">
              {displaySymptoms.map((s) => (
                <span key={s.label} className="dp-consult-symptom-tag">
                  <span className="material-symbols-outlined">{s.icon}</span>
                  {s.label}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className={`dp-glass dp-consult-risk-card dp-consult-risk-card--${insights.risk.variant}`}>
          <div className="dp-consult-risk-head">
            <span className="material-symbols-outlined">analytics</span>
            <h3 className="dp-consult-card-title">Risk Assessment</h3>
          </div>
          <div className="dp-consult-risk-body">
            <div className="dp-consult-risk-ring">
              <span>{insights.risk.ringLabel}</span>
            </div>
            <div>
              <p className="dp-consult-risk-title">{insights.risk.title}</p>
              <p className="dp-consult-risk-note">{insights.risk.note}</p>
            </div>
          </div>
          <blockquote className="dp-consult-risk-quote">&ldquo;{insights.risk.quote}&rdquo;</blockquote>
          {consult.emergency_flag && (
            <span className="dp-tag dp-tag--critical">Emergency flagged</span>
          )}
        </div>
      </div>

      <div className="dp-glass">
        <div className="dp-panel-head">
          <h2 className="dp-panel-title">Consultation History</h2>
          <button type="button" className="dp-link" onClick={onOpenChats}>
            Full transcripts →
          </button>
        </div>
        {consult.consultation_history.length === 0 ? (
          <p className="dp-muted-note" style={{ margin: 0 }}>
            No chatbot consultations recorded for this patient.
          </p>
        ) : (
          <div className="dp-consult-history-list">
            {consult.consultation_history.map((c) => (
              <article key={c.conversation_id} className="dp-consult-history-item">
                <div className="dp-consult-history-top">
                  <div>
                    <h4>{c.title}</h4>
                    <p className="dp-muted-note" style={{ margin: 0 }}>
                      {formatWhen(c.created_at)} · {c.message_count} messages
                    </p>
                  </div>
                  {c.emergency_flag && <span className="dp-tag dp-tag--critical">Emergency</span>}
                </div>
                {c.preview && <p className="dp-consult-history-preview">{c.preview}</p>}
                {c.detected_symptoms.length > 0 && (
                  <div className="dp-consult-history-symptoms">
                    {c.detected_symptoms.slice(0, 4).map((s) => (
                      <span key={s} className="dp-tag dp-tag--info">
                        {s}
                      </span>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </div>

      {(consult.conditions.length > 0 || consult.memory_facts.length > 0) && (
        <div className="dp-consult-clinical-grid">
          {consult.conditions.length > 0 && (
            <div className="dp-glass">
              <h3 className="dp-consult-card-title">Medical History</h3>
              <ul className="dp-consult-chip-list">
                {consult.conditions.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          )}
          {consult.memory_facts.length > 0 && (
            <div className="dp-glass">
              <h3 className="dp-consult-card-title">Patient Context (from chats)</h3>
              <ul className="dp-consult-facts">
                {consult.memory_facts.slice(0, 6).map((fact) => (
                  <li key={fact}>{fact}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
