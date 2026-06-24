import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api/client";
import VideoCallModal from "../../components/VideoCallModal";
import PreVisitPrepPanel from "../../components/doctor/PreVisitPrepPanel";
import ConsultationVisitSummaries from "../../components/doctor/ConsultationVisitSummaries";
import { useVideoConsultation } from "../../hooks/useVideoConsultation";
import {
  consultationModeIcon,
  consultationModeLabel,
  isVideoConsultation,
} from "../../utils/consultationMode";
import {
  formatDisplayDate,
  formatDoctorTime,
  patientInitials,
} from "../../utils/doctorPortal";
import {
  formatRiskLevelLabel,
  riskLevelCssVariant,
} from "../../utils/clinicalSummaryFormat";
import type { TranscriptAiSuggestions } from "../../types/consultationTranscript";
import { ConsultationSessionSkeleton } from "../../components/skeleton";

interface PrescriptionItem {
  medicine_name: string;
  strength: string;
  frequency: string;
  duration: string;
  instructions: string;
  source: string;
}

interface ConsultationData {
  id: string;
  status: string;
  chief_complaint: string | null;
  clinical_findings: string | null;
  diagnosis: string | null;
  doctor_notes: string | null;
  treatment_plan: string | null;
  follow_up_date: string | null;
  prescription_items: PrescriptionItem[];
  lab_orders: { test_code: string; test_name: string }[];
}

interface LabCatalogItem {
  test_code: string;
  test_name: string;
  keywords: string[];
  category?: string | null;
  description?: string | null;
  sort_order?: number;
}

interface LinkedReportPrep {
  report_id?: string;
  filename: string;
  summary?: string;
  abnormal?: { test?: string; value?: string; flag?: string }[];
  created_at?: string | null;
}

interface PrepData {
  appointment: {
    appointment_id: string;
    apt_id: string;
    date: string;
    time: string;
    status: string;
    consultation_mode: string;
    is_video?: boolean;
    video_room_id?: string | null;
    appointment_reason?: string | null;
  };
  patient: { patient_id: string; name: string };
  visit_type?: "report_discussion" | "symptom";
  appointment_reason?: string | null;
  linked_report?: LinkedReportPrep | null;
  ai_risk_level: string | null;
  ai_summary: Record<string, unknown>;
  consultation: ConsultationData;
  lab_catalog: LabCatalogItem[];
  can_start: boolean;
  is_completed: boolean;
}

interface AiSuggestions {
  batch_id: string;
  differential_considerations: string[];
  suggested_investigations: string[];
  matched_catalog_tests?: LabCatalogItem[];
  suggested_follow_up_days: number | null;
  clinical_notes_draft: string | null;
  suggested_medications: {
    medicine_name: string;
    strength?: string;
    frequency?: string;
    duration?: string;
    rationale?: string;
  }[];
  allergy_warnings: string[];
  disclaimer: string;
  patient_concerns?: string[];
  transcript_summary?: string | null;
  chief_complaint_suggestion?: string | null;
}

type AiFilledFields = {
  clinicalFindings: boolean;
  diagnosis: boolean;
  treatmentPlan: boolean;
  followUpDate: boolean;
  labs: boolean;
  meds: boolean;
};

const emptyMed = (): PrescriptionItem => ({
  medicine_name: "",
  strength: "",
  frequency: "",
  duration: "",
  instructions: "",
  source: "manual",
});

function investigationMatchesCatalog(investigation: string, item: LabCatalogItem): boolean {
  const text = investigation.toLowerCase().trim();
  if (!text) return false;
  const name = item.test_name.toLowerCase();
  const code = item.test_code.toLowerCase();
  if (name && (name.includes(text) || text.includes(name))) return true;
  if (code && text.includes(code)) return true;
  return (item.keywords ?? []).some((k) => text.includes(k.toLowerCase()));
}

function matchLabsFromInvestigations(
  catalog: LabCatalogItem[],
  investigations: string[],
): Set<string> {
  const codes = new Set<string>();
  for (const inv of investigations) {
    for (const lab of catalog) {
      if (investigationMatchesCatalog(inv, lab)) {
        codes.add(lab.test_code);
      }
    }
  }
  return codes;
}

function aiMatchedLabCodes(ai: AiSuggestions, catalog: LabCatalogItem[]): Set<string> {
  if (ai.matched_catalog_tests?.length) {
    return new Set(ai.matched_catalog_tests.map((t) => t.test_code));
  }
  return matchLabsFromInvestigations(catalog, ai.suggested_investigations);
}

function shiftIsoDate(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function buildPreVisitFindings(summary: Record<string, unknown>): string {
  const lines: string[] = [];
  const symptoms = (summary.symptoms as string[]) || [];
  const history = (summary.medical_history as string[]) || [];
  const allergies = (summary.allergies as string[]) || [];
  const meds = (summary.current_medications as { name: string; dosage?: string }[]) || [];

  if (symptoms.length) lines.push(`Presenting symptoms: ${symptoms.join(", ")}.`);
  if (summary.duration) lines.push(`Duration: ${String(summary.duration)}.`);
  if (history.length) lines.push(`Medical history: ${history.join(", ")}.`);
  if (meds.length) {
    lines.push(
      `Current medications: ${meds.map((m) => (m.dosage ? `${m.name} ${m.dosage}` : m.name)).join(", ")}.`,
    );
  }
  if (allergies.length) lines.push(`Known allergies: ${allergies.join(", ")}.`);
  return lines.join("\n");
}

function buildReportDiscussionSeed(summary: Record<string, unknown>): string {
  const linked = (summary.linked_report as LinkedReportPrep | undefined) || {};
  const lines: string[] = [];
  if (linked.summary) {
    lines.push("AI report summary (patient-facing):");
    lines.push(linked.summary);
  }
  const abnormal = linked.abnormal ?? [];
  if (abnormal.length > 0) {
    lines.push("");
    lines.push("Notable values discussed:");
    for (const item of abnormal.slice(0, 8)) {
      const flag = item.flag ? ` (${item.flag})` : "";
      lines.push(`• ${item.test ?? "Test"}: ${item.value ?? "—"}${flag}`);
    }
  }
  lines.push("");
  lines.push("Doctor discussion notes:");
  return lines.join("\n");
}

function isReportDiscussionVisit(prep: PrepData): boolean {
  return (
    prep.visit_type === "report_discussion" ||
    Boolean(prep.linked_report) ||
    Boolean(prep.appointment.appointment_reason?.toLowerCase().includes("report"))
  );
}

function formProgress(input: {
  chiefComplaint: string;
  clinicalFindings: string;
  diagnosis: string;
  treatmentPlan: string;
  followUpDate: string;
  meds: PrescriptionItem[];
  selectedLabs: Set<string>;
  labSectionMode: "unset" | "none" | "pick";
}): number {
  const labsResolved =
    input.labSectionMode === "none" ||
    (input.labSectionMode === "pick" && input.selectedLabs.size > 0);
  const checks = [
    input.chiefComplaint.trim().length > 0,
    input.clinicalFindings.trim().length > 0,
    input.diagnosis.trim().length > 0,
    input.treatmentPlan.trim().length > 0,
    Boolean(input.followUpDate),
    input.meds.some((m) => m.medicine_name.trim()),
    labsResolved,
  ];
  return Math.round((checks.filter(Boolean).length / checks.length) * 100);
}

function RibbonFact({
  label,
  labelTitle,
  value,
  icon,
  variant,
  wide,
}: {
  label: string;
  labelTitle?: string;
  value: string;
  icon: string;
  variant?: "risk" | "high" | "alert" | "neutral";
  wide?: boolean;
}) {
  return (
    <div
      className={`dp-consult-ribbon-fact${variant ? ` dp-consult-ribbon-fact--${variant}` : ""}${wide ? " dp-consult-ribbon-fact--wide" : ""}`}
      title={labelTitle ?? label}
    >
      <span className="dp-consult-ribbon-fact-label">
        <span className="dp-consult-ribbon-fact-icon material-symbols-outlined" aria-hidden>
          {icon}
        </span>
        <span className="dp-consult-ribbon-fact-label-text">{label}</span>
      </span>
      <span className="dp-consult-ribbon-fact-value">{value}</span>
    </div>
  );
}

function PreVisitRibbon({
  summary,
  riskLevel,
  hideTitle = false,
}: {
  summary: Record<string, unknown>;
  riskLevel: string | null;
  hideTitle?: boolean;
}) {
  const symptoms = (summary.symptoms as string[]) || [];
  const allergies = (summary.allergies as string[]) || [];
  const riskVariant = riskLevelCssVariant(riskLevel);
  const riskUiVariant = riskVariant === "high" ? "high" : riskVariant === "moderate" ? "risk" : "neutral";

  return (
    <div className="dp-consult-ribbon">
      <div className="dp-consult-ribbon-icon" aria-hidden>
        <span className="material-symbols-outlined filled-icon">auto_awesome</span>
      </div>
      <div className="dp-consult-ribbon-body">
        {!hideTitle && <p className="dp-consult-ribbon-title">Pre-visit summary</p>}
        <div className="dp-consult-ribbon-facts">
          {symptoms.length > 0 && (
            <RibbonFact label="Symptom" value={symptoms.join(", ")} icon="healing" />
          )}
          {summary.duration && (
            <RibbonFact label="Duration" value={String(summary.duration)} icon="schedule" />
          )}
          {riskLevel && (
            <RibbonFact
              label="Risk level"
              labelTitle="Triage risk level"
              value={formatRiskLevelLabel(riskLevel) ?? riskLevel}
              icon="monitor_heart"
              variant={riskUiVariant}
            />
          )}
          {allergies.map((a) => (
            <RibbonFact key={a} label="Allergy" value={a} icon="warning" variant="alert" />
          ))}
          <RibbonFact
            label="Complaint"
            labelTitle="Chief complaint"
            value={String(summary.chief_complaint || "—")}
            icon="clinical_notes"
            wide
          />
          {summary.recommended_specialty && (
            <RibbonFact
              label="Specialty"
              labelTitle="Recommended specialty"
              value={String(summary.recommended_specialty)}
              icon="medical_services"
              wide
            />
          )}
        </div>
      </div>
    </div>
  );
}

function PreVisitSummary({
  summary,
  riskLevel,
}: {
  summary: Record<string, unknown>;
  riskLevel: string | null;
}) {
  const symptoms = (summary.symptoms as string[]) || [];
  const history = (summary.medical_history as string[]) || [];
  const allergies = (summary.allergies as string[]) || [];
  const meds = (summary.current_medications as { name: string; dosage?: string }[]) || [];
  const riskVariant = riskLevelCssVariant(riskLevel);

  return (
    <div className="dp-consult-prep-grid">
      <div className="dp-consult-prep-main-card">
        <div className="dp-consult-section-head">
          <span className="material-symbols-outlined filled-icon">auto_awesome</span>
          <div>
            <h2>AI Pre-Visit Summary</h2>
            <p>Review triage data before you start documenting the visit.</p>
          </div>
        </div>
        {symptoms.length > 0 && (
          <div className="dp-consult-symptom-tags">
            {symptoms.map((s) => (
              <span key={s} className="dp-consult-symptom-tag">
                <span className="material-symbols-outlined">healing</span>
                {s}
              </span>
            ))}
          </div>
        )}
        <dl className="dp-consult-dl dp-consult-dl--rich">
          <dt>Chief complaint</dt>
          <dd>{String(summary.chief_complaint || "—")}</dd>
          <dt>Duration</dt>
          <dd>{String(summary.duration || "—")}</dd>
          <dt>Recommendation</dt>
          <dd>{String(summary.recommendation_text || "—")}</dd>
        </dl>
      </div>
      <div className="dp-consult-prep-side">
        {riskLevel && (
          <div className={`dp-consult-risk-card dp-consult-risk-card--${riskVariant}`}>
            <div className="dp-consult-risk-head">
              <span className="material-symbols-outlined">monitor_heart</span>
              <span>Triage risk</span>
            </div>
            <div className="dp-consult-risk-body">
              <div className="dp-consult-risk-ring">{formatRiskLevelLabel(riskLevel)?.charAt(0)}</div>
              <div>
                <p className="dp-consult-risk-title">{formatRiskLevelLabel(riskLevel)}</p>
                <p className="dp-consult-risk-note">From pre-visit assessment</p>
              </div>
            </div>
          </div>
        )}
        <div className="dp-consult-context-card">
          <h3 className="dp-consult-card-title">Patient context</h3>
          <ul className="dp-consult-chip-list">
            {history.length ? history.map((h) => <li key={h}>{h}</li>) : <li className="dp-consult-muted">No conditions</li>}
          </ul>
          {allergies.length > 0 && (
            <ul className="dp-consult-chip-list dp-consult-chip-list--alert">
              {allergies.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          )}
          {meds.length > 0 && (
            <ul className="dp-consult-med-list">
              {meds.map((m) => (
                <li key={m.name}>
                  <strong>{m.name}</strong>
                  {m.dosage && <span>{m.dosage}</span>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function ReportPreVisitSummary({
  consultFor,
  linkedReport,
  summary,
}: {
  consultFor: string;
  linkedReport: LinkedReportPrep;
  summary: Record<string, unknown>;
}) {
  const allergies = (summary.allergies as string[]) || [];
  const history = (summary.medical_history as string[]) || [];

  return (
    <div className="dp-consult-prep-grid">
      <div className="dp-consult-prep-main-card dp-report-discussion-card">
        <div className="dp-consult-section-head">
          <span className="material-symbols-outlined filled-icon">description</span>
          <div>
            <h2>Report discussion pre-visit</h2>
            <p>Review the uploaded report and AI summary before documenting your discussion.</p>
          </div>
        </div>
        <dl className="dp-consult-dl dp-consult-dl--rich">
          <dt>Consult for</dt>
          <dd>{consultFor}</dd>
          <dt>Uploaded report</dt>
          <dd>{linkedReport.filename}</dd>
        </dl>
        {linkedReport.summary ? (
          <div className="dp-report-ai-summary-box">
            <p className="dp-report-ai-summary-label">AI-generated report description</p>
            <p>{linkedReport.summary}</p>
          </div>
        ) : null}
        {(linkedReport.abnormal ?? []).length > 0 && (
          <ul className="dp-report-review-abnormal">
            {(linkedReport.abnormal ?? []).slice(0, 8).map((item) => (
              <li key={`${item.test}-${item.value}`}>
                {item.test}: {item.value}
                {item.flag ? ` (${item.flag})` : ""}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="dp-consult-prep-side">
        <div className="dp-consult-context-card">
          <h3 className="dp-consult-card-title">Patient context</h3>
          <ul className="dp-consult-chip-list">
            {history.length ? history.map((h) => <li key={h}>{h}</li>) : <li className="dp-consult-muted">No conditions</li>}
          </ul>
          {allergies.length > 0 && (
            <ul className="dp-consult-chip-list dp-consult-chip-list--alert">
              {allergies.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function ReportPreVisitRibbon({
  consultFor,
  linkedReport,
  hideTitle = false,
}: {
  consultFor: string;
  linkedReport: LinkedReportPrep;
  hideTitle?: boolean;
}) {
  return (
    <div className="dp-consult-ribbon dp-consult-ribbon--report">
      <div className="dp-consult-ribbon-icon" aria-hidden>
        <span className="material-symbols-outlined filled-icon">description</span>
      </div>
      <div className="dp-consult-ribbon-body">
        {!hideTitle && <p className="dp-consult-ribbon-title">Report discussion</p>}
        <div className="dp-consult-ribbon-facts">
          <RibbonFact label="Consult for" value={consultFor} icon="medical_information" wide />
          <RibbonFact label="Report" value={linkedReport.filename} icon="upload_file" wide />
        </div>
      </div>
    </div>
  );
}

function SmartField({
  label,
  value,
  onChange,
  rows = 3,
  placeholder,
  disabled,
  aiFilled,
  fieldClassName,
  children,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  rows?: number;
  placeholder?: string;
  disabled?: boolean;
  aiFilled?: boolean;
  fieldClassName?: string;
  children?: ReactNode;
}) {
  return (
    <div className={`dp-smart-field${aiFilled ? " dp-smart-field--ai" : ""}${fieldClassName ? ` ${fieldClassName}` : ""}`}>
      <div className="dp-smart-field-head">
        <span>{label}</span>
        {aiFilled && (
          <span className="dp-smart-field-badge">
            <span className="material-symbols-outlined">auto_awesome</span>
            AI filled
          </span>
        )}
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={rows}
        placeholder={placeholder}
        disabled={disabled}
      />
      {children}
    </div>
  );
}

export default function ConsultationSession() {
  const { appointmentId } = useParams<{ appointmentId: string }>();
  const navigate = useNavigate();
  const [prep, setPrep] = useState<PrepData | null>(null);
  const [phase, setPhase] = useState<"prep" | "active" | "done">("prep");
  const redirectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draftSaved, setDraftSaved] = useState(false);
  const [ai, setAi] = useState<AiSuggestions | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiApplied, setAiApplied] = useState(false);
  const [aiFilled, setAiFilled] = useState<AiFilledFields>({
    clinicalFindings: false,
    diagnosis: false,
    treatmentPlan: false,
    followUpDate: false,
    labs: false,
    meds: false,
  });
  const [selectedAiMeds, setSelectedAiMeds] = useState<Set<string>>(new Set());
  const snapshotRef = useRef<{
    clinicalFindings: string;
    diagnosis: string;
    treatmentPlan: string;
    followUpDate: string;
    meds: PrescriptionItem[];
    selectedLabs: Set<string>;
  } | null>(null);
  const transcriptApplyOnStartRef = useRef<TranscriptAiSuggestions | null>(null);
  const [transcriptQueuedForApply, setTranscriptQueuedForApply] = useState(false);

  const [chiefComplaint, setChiefComplaint] = useState("");
  const [clinicalFindings, setClinicalFindings] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [doctorNotes, setDoctorNotes] = useState("");
  const [treatmentPlan, setTreatmentPlan] = useState("");
  const [followUpDate, setFollowUpDate] = useState("");
  const [meds, setMeds] = useState<PrescriptionItem[]>([emptyMed()]);
  const [selectedLabs, setSelectedLabs] = useState<Set<string>>(new Set());
  const [labSectionMode, setLabSectionMode] = useState<"unset" | "none" | "pick">("unset");
  const [labCatalog, setLabCatalog] = useState<LabCatalogItem[]>([]);
  const [videoOpen, setVideoOpen] = useState(false);
  const {
    session: videoSession,
    loading: videoLoading,
    error: videoError,
    joinAppointment: joinVideo,
    reset: resetVideo,
  } = useVideoConsultation("doctor");

  const progress = useMemo(
    () =>
      formProgress({
        chiefComplaint,
        clinicalFindings,
        diagnosis,
        treatmentPlan,
        followUpDate,
        meds,
        selectedLabs,
        labSectionMode,
      }),
    [chiefComplaint, clinicalFindings, diagnosis, treatmentPlan, followUpDate, meds, selectedLabs, labSectionMode],
  );

  const prepRef = useRef<PrepData | null>(null);
  prepRef.current = prep;

  const loadPrep = useCallback(async () => {
    if (!appointmentId) return;
    const silentRefresh = Boolean(prepRef.current);
    if (!silentRefresh) {
      setLoading(true);
    }
    setError(null);
    try {
      const data = await api<PrepData>(
        `/api/v1/doctor/appointments/${appointmentId}/consultation-prep`,
      );
      setPrep(data);
      setLabCatalog(data.lab_catalog ?? []);
      const c = data.consultation;
      setChiefComplaint(c.chief_complaint || String(data.ai_summary.chief_complaint || ""));
      setClinicalFindings(c.clinical_findings || "");
      setDiagnosis(c.diagnosis || "");
      setDoctorNotes(c.doctor_notes || "");
      setTreatmentPlan(c.treatment_plan || "");
      setFollowUpDate(c.follow_up_date || "");
      if (c.prescription_items?.length) setMeds(c.prescription_items);
      if (c.lab_orders?.length) {
        setSelectedLabs(new Set(c.lab_orders.map((l) => l.test_code)));
        setLabSectionMode("pick");
      } else {
        setLabSectionMode("unset");
      }
      if (data.is_completed || c.status === "completed") {
        setPhase("done");
      } else if (c.status === "in_progress" || c.status === "draft") {
        setPhase("active");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load consultation");
    } finally {
      if (!silentRefresh) {
        setLoading(false);
      }
    }
  }, [appointmentId]);

  useEffect(() => {
    return () => {
      if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current);
    };
  }, []);

  const returnToPatientVisits = useCallback(
    (patientId: string) => {
      navigate(`/doctor/patients/${patientId}?tab=appointments`);
    },
    [navigate],
  );

  const scheduleReturnToPatientVisits = useCallback(
    (patientId: string, delayMs = 1200) => {
      if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current);
      redirectTimerRef.current = setTimeout(() => {
        returnToPatientVisits(patientId);
      }, delayMs);
    },
    [returnToPatientVisits],
  );

  useEffect(() => {
    loadPrep();
  }, [loadPrep]);

  const seedFromPreVisit = () => {
    if (!prep || clinicalFindings.trim()) return;
    if (isReportDiscussionVisit(prep)) {
      setClinicalFindings(buildReportDiscussionSeed(prep.ai_summary));
      return;
    }
    setClinicalFindings(buildPreVisitFindings(prep.ai_summary));
  };

  const buildPayload = () => ({
    chief_complaint: chiefComplaint || null,
    clinical_findings: clinicalFindings || null,
    diagnosis: diagnosis || null,
    doctor_notes: doctorNotes || null,
    treatment_plan: treatmentPlan || null,
    follow_up_date: followUpDate || null,
    prescription_items: meds.filter((m) => m.medicine_name.trim()),
    lab_orders: labCatalog
      .filter((l) => selectedLabs.has(l.test_code))
      .map((l) => ({
        test_code: l.test_code,
        test_name: l.test_name,
      })),
  });

  const applyAiToForm = useCallback(
    (data: AiSuggestions, autoApplyMeds = true) => {
      snapshotRef.current = {
        clinicalFindings,
        diagnosis,
        treatmentPlan,
        followUpDate,
        meds: [...meds],
        selectedLabs: new Set(selectedLabs),
      };

      const filled: AiFilledFields = {
        clinicalFindings: false,
        diagnosis: false,
        treatmentPlan: false,
        followUpDate: false,
        labs: false,
        meds: false,
      };

      if (data.chief_complaint_suggestion && !chiefComplaint.trim()) {
        setChiefComplaint(data.chief_complaint_suggestion);
      }

      if (data.clinical_notes_draft) {
        setClinicalFindings((prev) =>
          prev.trim() ? `${prev.trim()}\n\n${data.clinical_notes_draft}` : data.clinical_notes_draft!,
        );
        filled.clinicalFindings = true;
      }

      if (data.differential_considerations.length > 0) {
        if (!diagnosis.trim()) {
          setDiagnosis(data.differential_considerations[0]);
          filled.diagnosis = true;
        }
        if (!treatmentPlan.trim()) {
          const plan = data.differential_considerations
            .slice(0, 3)
            .map((d, i) => `${i + 1}. Consider ${d}`)
            .join("\n");
          setTreatmentPlan(plan);
          filled.treatmentPlan = true;
        }
      }

      if (data.suggested_follow_up_days != null) {
        setFollowUpDate(shiftIsoDate(new Date().toISOString().slice(0, 10), data.suggested_follow_up_days));
        filled.followUpDate = true;
      }

      const labCodes =
        data.matched_catalog_tests?.length
          ? new Set(data.matched_catalog_tests.map((t) => t.test_code))
          : matchLabsFromInvestigations(labCatalog, data.suggested_investigations);
      if (labCodes.size > 0) {
        setSelectedLabs((prev) => new Set([...prev, ...labCodes]));
        setLabSectionMode("pick");
        filled.labs = true;
      }

      if (autoApplyMeds && data.suggested_medications.length > 0) {
        const names = new Set(data.suggested_medications.map((m) => m.medicine_name.toLowerCase()));
        setSelectedAiMeds(names);
        const existing = meds.filter((m) => m.medicine_name.trim());
        const newMeds = data.suggested_medications.map((m) => ({
          medicine_name: m.medicine_name,
          strength: m.strength || "",
          frequency: m.frequency || "",
          duration: m.duration || "",
          instructions: m.rationale || "",
          source: "ai_suggested_accepted",
        }));
        setMeds([...existing, ...newMeds, emptyMed()]);
        filled.meds = true;
      } else if (data.suggested_medications.length > 0) {
        setSelectedAiMeds(new Set(data.suggested_medications.map((m) => m.medicine_name.toLowerCase())));
      }

      setAiFilled(filled);
      setAiApplied(true);
    },
    [clinicalFindings, diagnosis, treatmentPlan, followUpDate, meds, selectedLabs, labCatalog],
  );

  const revertAiFill = () => {
    const snap = snapshotRef.current;
    if (!snap) return;
    setClinicalFindings(snap.clinicalFindings);
    setDiagnosis(snap.diagnosis);
    setTreatmentPlan(snap.treatmentPlan);
    setFollowUpDate(snap.followUpDate);
    setMeds(snap.meds);
    setSelectedLabs(snap.selectedLabs);
    setLabSectionMode(snap.selectedLabs.size > 0 ? "pick" : "unset");
    setAiApplied(false);
    setAiFilled({
      clinicalFindings: false,
      diagnosis: false,
      treatmentPlan: false,
      followUpDate: false,
      labs: false,
      meds: false,
    });
    setSelectedAiMeds(new Set());
  };

  const generateAndFill = async () => {
    if (!appointmentId) return;
    setAiLoading(true);
    setError(null);
    try {
      const data = await api<AiSuggestions>(
        `/api/v1/doctor/appointments/${appointmentId}/consultation/ai-suggestions`,
        { method: "POST" },
      );
      setAi(data);
      applyAiToForm(data, true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "AI suggestions unavailable");
    } finally {
      setAiLoading(false);
    }
  };

  const addSelectedAiMeds = () => {
    if (!ai) return;
    const toAdd = ai.suggested_medications.filter((m) =>
      selectedAiMeds.has(m.medicine_name.toLowerCase()),
    );
    const existing = meds.filter((m) => m.medicine_name.trim());
    const existingNames = new Set(existing.map((m) => m.medicine_name.toLowerCase()));
    const newMeds = toAdd
      .filter((m) => !existingNames.has(m.medicine_name.toLowerCase()))
      .map((m) => ({
        medicine_name: m.medicine_name,
        strength: m.strength || "",
        frequency: m.frequency || "",
        duration: m.duration || "",
        instructions: m.rationale || "",
        source: "ai_suggested_accepted",
      }));
    if (newMeds.length) {
      setMeds([...existing, ...newMeds, emptyMed()]);
      setAiFilled((f) => ({ ...f, meds: true }));
    }
  };

  const startConsultation = async () => {
    if (!appointmentId) return;
    setSaving(true);
    setError(null);
    try {
      await api(`/api/v1/doctor/appointments/${appointmentId}/consultation/start`, { method: "POST" });
      setPhase("active");
      await loadPrep();
      const queued = transcriptApplyOnStartRef.current;
      if (queued) {
        const suggestions = queued as AiSuggestions;
        setAi(suggestions);
        applyAiToForm(suggestions, false);
        transcriptApplyOnStartRef.current = null;
        setTranscriptQueuedForApply(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start consultation");
    } finally {
      setSaving(false);
    }
  };

  const handleJoinVideo = async () => {
    if (!appointmentId) return;
    setVideoOpen(true);
    try {
      await joinVideo(appointmentId);
    } catch {
      // handled in hook
    }
  };

  const closeVideo = () => {
    setVideoOpen(false);
    resetVideo();
  };

  const saveDraft = async () => {
    if (!appointmentId) return;
    setSaving(true);
    setError(null);
    setDraftSaved(false);
    try {
      await api(`/api/v1/doctor/appointments/${appointmentId}/consultation`, {
        method: "PUT",
        body: JSON.stringify(buildPayload()),
      });
      setDraftSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const completeConsultation = async () => {
    if (!appointmentId || !prep) return;
    if (!diagnosis.trim() && !treatmentPlan.trim()) {
      setError("Diagnosis or treatment plan is required.");
      return;
    }
    const patientId = prep.patient.patient_id;
    setSaving(true);
    setError(null);
    try {
      await api(`/api/v1/doctor/appointments/${appointmentId}/complete-consultation`, {
        method: "POST",
        body: JSON.stringify({
          ...buildPayload(),
          doctor_signature_name: localStorage.getItem("user_name") || "Doctor",
        }),
      });
      setPhase("done");
      await loadPrep();
      scheduleReturnToPatientVisits(patientId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not complete consultation");
    } finally {
      setSaving(false);
    }
  };

  const handleTranscriptAnalyze = useCallback(
    (data: TranscriptAiSuggestions) => {
      const suggestions = data as AiSuggestions;
      setAi(suggestions);
      applyAiToForm(suggestions, false);
      setVideoOpen(false);
    },
    [applyAiToForm],
  );

  const handleInVisitTranscriptAnalyze = useCallback((data: TranscriptAiSuggestions) => {
    setAi(data as AiSuggestions);
  }, []);

  const handleApplyInVisitToForm = useCallback(
    (data: TranscriptAiSuggestions) => {
      const suggestions = data as AiSuggestions;
      setAi(suggestions);
      applyAiToForm(suggestions, false);
    },
    [applyAiToForm],
  );

  const handlePrepTranscriptAnalyze = useCallback((data: TranscriptAiSuggestions) => {
    setAi(data as AiSuggestions);
  }, []);

  const handlePrepApplyTranscriptToForm = useCallback((data: TranscriptAiSuggestions) => {
    setAi(data as AiSuggestions);
    transcriptApplyOnStartRef.current = data;
    setTranscriptQueuedForApply(true);
  }, []);

  const videoModal = (
    <VideoCallModal
      open={videoOpen}
      loading={videoLoading}
      error={videoError}
      session={videoSession}
      role="doctor"
      appointmentId={appointmentId}
      onClose={closeVideo}
      onTranscriptAnalyze={handleTranscriptAnalyze}
    />
  );

  if (loading && !prep) {
    return (
      <>
        <div className="dp-consult-workspace">
          <ConsultationSessionSkeleton />
        </div>
        {videoModal}
      </>
    );
  }

  if (!prep) {
    return (
      <>
        <div className="dp-consult-workspace">
          <p className="dp-error-text">{error || "Consultation not found"}</p>
          <Link to="/doctor" className="dp-btn dp-btn--outline">Back to dashboard</Link>
        </div>
        {videoModal}
      </>
    );
  }

  const stepIndex = phase === "prep" ? 0 : phase === "active" ? 1 : 2;
  const reportVisit = isReportDiscussionVisit(prep);
  const steps = reportVisit
    ? ["Review report", "Document discussion", "Complete"]
    : ["Review pre-visit", "Document visit", "Complete"];
  const consultFor =
    prep.appointment_reason ||
    String(prep.ai_summary.consult_for || "Medical Report Review & Consultation");
  const linkedReport = prep.linked_report || (prep.ai_summary.linked_report as LinkedReportPrep | undefined);
  const aiLabCodes = ai ? aiMatchedLabCodes(ai, labCatalog) : new Set<string>();
  const selectedLabNames = labCatalog
    .filter((l) => selectedLabs.has(l.test_code))
    .map((l) => l.test_name);

  const addAllAiSuggestedLabs = () => {
    if (!ai) return;
    const codes = aiMatchedLabCodes(ai, labCatalog);
    if (codes.size === 0) return;
    setLabSectionMode("pick");
    setSelectedLabs((prev) => new Set([...prev, ...codes]));
    setAiFilled((f) => ({ ...f, labs: true }));
  };
  const unaddedAiMeds =
    ai?.suggested_medications.filter(
      (m) =>
        selectedAiMeds.has(m.medicine_name.toLowerCase()) &&
        !meds.some((x) => x.medicine_name.toLowerCase() === m.medicine_name.toLowerCase()),
    ) ?? [];

  const visitMode = prep.appointment.consultation_mode;
  const visitIsVideo = isVideoConsultation(prep.appointment);
  const modeLabel = consultationModeLabel(visitMode, prep.appointment.is_video);
  const modeIcon = consultationModeIcon(visitMode, prep.appointment.is_video);

  return (
    <div className="dp-consult-workspace">
      <header className="dp-consult-hero">
        <div className="dp-consult-hero-main">
          <Link to={`/doctor/patients/${prep.patient.patient_id}`} className="dp-consult-back">
            <span className="material-symbols-outlined">arrow_back</span>
            Back to patient chart
          </Link>
          <div className="dp-consult-hero-row">
            <div className="dp-consult-hero-avatar">{patientInitials(prep.patient.name)}</div>
            <div>
              <h1>{prep.patient.name}</h1>
              <div className="dp-consult-hero-meta">
                <span className="dp-consult-meta-pill">
                  <span className="material-symbols-outlined">badge</span>
                  {prep.appointment.apt_id}
                </span>
                <span className="dp-consult-meta-pill">
                  <span className="material-symbols-outlined">calendar_today</span>
                  {formatDisplayDate(prep.appointment.date)} · {formatDoctorTime(prep.appointment.time)}
                </span>
                <span
                  className={`dp-consult-meta-pill dp-consult-meta-pill--mode${visitIsVideo ? " dp-consult-meta-pill--mode-video" : ""}`}
                >
                  <span className="material-symbols-outlined">{modeIcon}</span>
                  {modeLabel}
                </span>
              </div>
            </div>
          </div>
        </div>
        {phase === "active" && (
          <div className="dp-consult-progress-card">
            <div className="dp-consult-progress-head">
              <span className="dp-consult-phase">Progress</span>
              <span className="dp-consult-percent">{progress}%</span>
            </div>
            <div className="dp-consult-progress-bar">
              <div className="dp-consult-progress-fill" style={{ width: `${progress}%` }} />
            </div>
          </div>
        )}
      </header>

      <nav className="dp-consult-stepper" aria-label="Consultation progress">
        {steps.map((label, i) => (
          <div
            key={label}
            className={`dp-consult-stepper-item${i < stepIndex ? " dp-consult-stepper-item--done" : ""}${i === stepIndex ? " dp-consult-stepper-item--active" : ""}`}
          >
            <span className="dp-consult-stepper-dot">
              {i < stepIndex ? <span className="material-symbols-outlined">check</span> : i + 1}
            </span>
            <span className="dp-consult-stepper-label">{label}</span>
          </div>
        ))}
      </nav>

      {error && (
        <div className="dp-consult-error" role="alert">
          <span className="material-symbols-outlined">error</span>
          {error}
        </div>
      )}

      {phase === "prep" && prep && (
        <PreVisitPrepPanel
          appointmentId={appointmentId!}
          patientId={prep.patient.patient_id}
          patientName={prep.patient.name}
          isVideo={visitIsVideo}
          reportVisit={reportVisit}
          canStart={prep.can_start}
          saving={saving}
          onStartConsultation={startConsultation}
          onTranscriptAnalyze={handlePrepTranscriptAnalyze}
          onApplyTranscriptToForm={handlePrepApplyTranscriptToForm}
          transcriptApplyQueued={transcriptQueuedForApply}
        >
          {reportVisit && linkedReport ? (
            <ReportPreVisitSummary
              consultFor={consultFor}
              linkedReport={linkedReport}
              summary={prep.ai_summary}
            />
          ) : (
            <PreVisitSummary summary={prep.ai_summary} riskLevel={prep.ai_risk_level} />
          )}
        </PreVisitPrepPanel>
      )}

      {(phase === "active" || phase === "done") && (
        <>
          {visitIsVideo && phase === "active" && (
            <section className="dp-consult-video-panel" aria-label="Video room">
              <div className="dp-consult-video-panel-head">
                <span className="material-symbols-outlined">videocam</span>
                <div>
                  <strong>Video room</strong>
                  <p>Join the live call while documenting this consultation.</p>
                </div>
                <div className="dp-consult-video-panel-actions">
                  <button
                    type="button"
                    className="dp-btn dp-btn--outline dp-btn--sm"
                    onClick={() => void handleJoinVideo()}
                  >
                    Join video call
                  </button>
                </div>
              </div>
            </section>
          )}

          {reportVisit && linkedReport ? (
            <ConsultationVisitSummaries
              appointmentId={appointmentId!}
              layout="active"
              autoAnalyzeEnabled={phase === "active" && videoOpen}
              onTranscriptAnalyze={handleInVisitTranscriptAnalyze}
              onApplyTranscriptToForm={handleApplyInVisitToForm}
              preVisit={<ReportPreVisitRibbon consultFor={consultFor} linkedReport={linkedReport} hideTitle />}
            />
          ) : (
            <ConsultationVisitSummaries
              appointmentId={appointmentId!}
              layout="active"
              autoAnalyzeEnabled={phase === "active" && videoOpen}
              onTranscriptAnalyze={handleInVisitTranscriptAnalyze}
              onApplyTranscriptToForm={handleApplyInVisitToForm}
              preVisit={<PreVisitRibbon summary={prep.ai_summary} riskLevel={prep.ai_risk_level} hideTitle />}
            />
          )}

          {phase === "active" && (
            <div className={`dp-ai-command${aiApplied ? " dp-ai-command--applied" : ""}`}>
              <div className="dp-ai-command-glow" aria-hidden />
              <div className="dp-ai-command-inner">
                <div className="dp-ai-command-text">
                  <span className="material-symbols-outlined filled-icon">psychology</span>
                  <div>
                    <strong>AI Smart Assist</strong>
                    <p>
                      {aiApplied
                        ? "Suggestions applied to the form below — review, edit, then complete."
                        : reportVisit
                          ? "One click drafts discussion notes, interpretation, and follow-up from the linked report."
                          : "One click drafts findings, diagnosis, labs, follow-up & prescriptions from pre-visit data."}
                    </p>
                  </div>
                </div>
                <div className="dp-ai-command-actions">
                  {aiApplied ? (
                    <button type="button" className="dp-btn dp-btn--ghost" onClick={revertAiFill}>
                      <span className="material-symbols-outlined">undo</span>
                      Undo AI fill
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="dp-btn dp-btn--ai"
                    disabled={aiLoading}
                    onClick={generateAndFill}
                  >
                    <span className="material-symbols-outlined">auto_awesome</span>
                    {aiLoading ? "Generating…" : aiApplied ? "Regenerate & fill" : "Generate & fill form"}
                  </button>
                </div>
              </div>
              {ai && ai.allergy_warnings.length > 0 && (
                <div className="dp-ai-command-alerts">
                  {ai.allergy_warnings.map((w) => (
                    <span key={w} className="dp-ai-alert-chip">
                      <span className="material-symbols-outlined">warning</span>
                      {w}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          <div className="dp-consult-unified">
            <section className="dp-consult-form-section dp-consult-form-section--primary">
              <header className="dp-consult-section-head">
                <span className="material-symbols-outlined">clinical_notes</span>
                <div>
                  <h2>{reportVisit ? "Report discussion" : "Clinical assessment"}</h2>
                  <p>
                    {reportVisit
                      ? "Document what you discussed about the report — edit the AI summary and add your clinical interpretation."
                      : "Document the visit — tap any AI chip to use a suggestion instantly."}
                  </p>
                </div>
              </header>

              <div className="dp-consult-field-stack">
                <SmartField
                  label={reportVisit ? "Consult for" : "Chief complaint"}
                  value={chiefComplaint}
                  onChange={setChiefComplaint}
                  rows={2}
                  placeholder={reportVisit ? "Medical Report Review & Consultation" : "Patient's primary concern"}
                  disabled={phase === "done"}
                />

                <SmartField
                  label={reportVisit ? "Report discussion & clinical notes" : "Clinical findings"}
                  value={clinicalFindings}
                  onChange={(v) => {
                    setClinicalFindings(v);
                    if (aiFilled.clinicalFindings) setAiFilled((f) => ({ ...f, clinicalFindings: false }));
                  }}
                  rows={reportVisit ? 8 : 5}
                  placeholder={
                    reportVisit
                      ? "AI report summary, your interpretation, and what you explained to the patient"
                      : "Examination notes, vitals, observations"
                  }
                  disabled={phase === "done"}
                  aiFilled={aiFilled.clinicalFindings}
                  fieldClassName="dp-smart-field--clinical"
                >
                  {phase === "active" && !clinicalFindings.trim() && (
                    <button type="button" className="dp-inline-suggest" onClick={seedFromPreVisit}>
                      <span className="material-symbols-outlined">content_paste</span>
                      {reportVisit
                        ? "Insert AI report summary for discussion"
                        : "Insert triage context (symptoms, history)"}
                    </button>
                  )}
                </SmartField>

                <SmartField
                  label="Diagnosis"
                  value={diagnosis}
                  onChange={(v) => {
                    setDiagnosis(v);
                    if (aiFilled.diagnosis) setAiFilled((f) => ({ ...f, diagnosis: false }));
                  }}
                  rows={2}
                  placeholder="Primary diagnosis"
                  disabled={phase === "done"}
                  aiFilled={aiFilled.diagnosis}
                >
                  {ai && ai.differential_considerations.length > 0 && phase === "active" && (
                    <div className="dp-suggest-chips">
                      <span className="dp-suggest-chips-label">Tap to use:</span>
                      {ai.differential_considerations.map((d) => (
                        <button
                          key={d}
                          type="button"
                          className={`dp-suggest-chip${diagnosis === d ? " dp-suggest-chip--active" : ""}`}
                          onClick={() => setDiagnosis(d)}
                        >
                          {d}
                        </button>
                      ))}
                    </div>
                  )}
                </SmartField>

                <SmartField
                  label="Doctor notes (private)"
                  value={doctorNotes}
                  onChange={setDoctorNotes}
                  rows={2}
                  placeholder="Internal notes only"
                  disabled={phase === "done"}
                />
              </div>
            </section>

            <section className="dp-consult-form-section">
              <header className="dp-consult-section-head">
                <span className="material-symbols-outlined">assignment</span>
                <div>
                  <h2>Treatment &amp; follow-up</h2>
                </div>
              </header>
              <div className="dp-consult-field-stack">
                <SmartField
                  label="Treatment plan"
                  value={treatmentPlan}
                  onChange={(v) => {
                    setTreatmentPlan(v);
                    if (aiFilled.treatmentPlan) setAiFilled((f) => ({ ...f, treatmentPlan: false }));
                  }}
                  rows={4}
                  placeholder="Medications, lifestyle advice, referrals"
                  disabled={phase === "done"}
                  aiFilled={aiFilled.treatmentPlan}
                />
                <div className={`dp-smart-field dp-smart-field--inline${aiFilled.followUpDate ? " dp-smart-field--ai" : ""}`}>
                  <div className="dp-smart-field-head">
                    <span>Follow-up date</span>
                    {aiFilled.followUpDate && ai?.suggested_follow_up_days != null && (
                      <span className="dp-smart-field-badge">
                        AI: +{ai.suggested_follow_up_days} days
                      </span>
                    )}
                  </div>
                  <input
                    type="date"
                    value={followUpDate}
                    onChange={(e) => {
                      setFollowUpDate(e.target.value);
                      if (aiFilled.followUpDate) setAiFilled((f) => ({ ...f, followUpDate: false }));
                    }}
                    disabled={phase === "done"}
                  />
                </div>
              </div>
            </section>

            <section className="dp-consult-form-section">
              <header className="dp-consult-section-head">
                <span className="material-symbols-outlined">medication</span>
                <div>
                  <h2>Prescription</h2>
                  {unaddedAiMeds.length > 0 && phase === "active" && (
                    <button type="button" className="dp-inline-suggest dp-inline-suggest--primary" onClick={addSelectedAiMeds}>
                      <span className="material-symbols-outlined">add_circle</span>
                      Add {unaddedAiMeds.length} selected AI medicine{unaddedAiMeds.length > 1 ? "s" : ""}
                    </button>
                  )}
                </div>
              </header>

              {ai && ai.suggested_medications.length > 0 && phase === "active" && (
                <div className="dp-ai-rx-suggestions">
                  {ai.suggested_medications.map((m) => {
                    const key = m.medicine_name.toLowerCase();
                    const inRx = meds.some((x) => x.medicine_name.toLowerCase() === key);
                    const selected = selectedAiMeds.has(key);
                    return (
                      <label
                        key={m.medicine_name}
                        className={`dp-ai-rx-card${selected ? " dp-ai-rx-card--on" : ""}${inRx ? " dp-ai-rx-card--added" : ""}`}
                      >
                        <input
                          type="checkbox"
                          checked={selected}
                          disabled={inRx}
                          onChange={(e) => {
                            const next = new Set(selectedAiMeds);
                            if (e.target.checked) next.add(key);
                            else next.delete(key);
                            setSelectedAiMeds(next);
                          }}
                        />
                        <div>
                          <strong>{m.medicine_name}</strong>
                          <span>{[m.strength, m.frequency, m.duration].filter(Boolean).join(" · ")}</span>
                          {m.rationale && <p>{m.rationale}</p>}
                        </div>
                        {inRx && <span className="dp-ai-rx-added">Added</span>}
                      </label>
                    );
                  })}
                </div>
              )}

              <div className="dp-consult-rx-table-wrap">
                <table className="dp-consult-rx-table">
                  <thead>
                    <tr>
                      <th>Medicine</th>
                      <th>Strength</th>
                      <th>Frequency</th>
                      <th>Duration</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {meds.map((med, idx) => (
                      <tr key={idx} className={med.source === "ai_suggested_accepted" ? "dp-consult-rx-row--ai" : ""}>
                        <td>
                          <input
                            placeholder="Paracetamol"
                            value={med.medicine_name}
                            disabled={phase === "done"}
                            onChange={(e) => {
                              const next = [...meds];
                              next[idx] = { ...med, medicine_name: e.target.value };
                              setMeds(next);
                            }}
                          />
                        </td>
                        <td>
                          <input
                            placeholder="500mg"
                            value={med.strength}
                            disabled={phase === "done"}
                            onChange={(e) => {
                              const next = [...meds];
                              next[idx] = { ...med, strength: e.target.value };
                              setMeds(next);
                            }}
                          />
                        </td>
                        <td>
                          <input
                            placeholder="Twice daily"
                            value={med.frequency}
                            disabled={phase === "done"}
                            onChange={(e) => {
                              const next = [...meds];
                              next[idx] = { ...med, frequency: e.target.value };
                              setMeds(next);
                            }}
                          />
                        </td>
                        <td>
                          <input
                            placeholder="5 days"
                            value={med.duration}
                            disabled={phase === "done"}
                            onChange={(e) => {
                              const next = [...meds];
                              next[idx] = { ...med, duration: e.target.value };
                              setMeds(next);
                            }}
                          />
                        </td>
                        <td>
                          {phase !== "done" && meds.length > 1 && (
                            <button
                              type="button"
                              className="dp-consult-rx-remove"
                              aria-label="Remove"
                              onClick={() => setMeds(meds.filter((_, i) => i !== idx))}
                            >
                              <span className="material-symbols-outlined">close</span>
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {phase !== "done" && (
                <button type="button" className="dp-btn dp-btn--outline dp-consult-add-med" onClick={() => setMeds([...meds, emptyMed()])}>
                  <span className="material-symbols-outlined">add</span>
                  Add medicine manually
                </button>
              )}
            </section>

            <section className="dp-consult-form-section dp-consult-form-section--labs">
              <header className="dp-consult-section-head">
                <span className="material-symbols-outlined">science</span>
                <div>
                  <h2>Diagnostic tests</h2>
                  <p className="dp-consult-section-hint">
                    Does this patient need blood work or other tests today?
                  </p>
                </div>
              </header>

              {phase === "done" ? (
                <div className="dp-lab-outcome">
                  {selectedLabNames.length > 0 ? (
                    <>
                      <span className="material-symbols-outlined">biotech</span>
                      <div>
                        <strong>Tests ordered</strong>
                        <p>{selectedLabNames.join(", ")}</p>
                      </div>
                    </>
                  ) : (
                    <>
                      <span className="material-symbols-outlined">check_circle</span>
                      <div>
                        <strong>No tests required</strong>
                        <p>No diagnostic tests were ordered for this visit.</p>
                      </div>
                    </>
                  )}
                </div>
              ) : (
                <>
                  <div className="dp-lab-choice-row" role="group" aria-label="Tests needed for this visit?">
                    <button
                      type="button"
                      className={`dp-lab-choice-card${labSectionMode === "none" ? " dp-lab-choice-card--on" : ""}`}
                      onClick={() => {
                        setLabSectionMode("none");
                        setSelectedLabs(new Set());
                        setAiFilled((f) => ({ ...f, labs: false }));
                      }}
                    >
                      <span className="material-symbols-outlined">check_circle</span>
                      <strong>No tests required</strong>
                      <span>Patient does not need lab work today</span>
                    </button>
                    <button
                      type="button"
                      className={`dp-lab-choice-card${labSectionMode === "pick" ? " dp-lab-choice-card--on" : ""}`}
                      onClick={() => setLabSectionMode("pick")}
                    >
                      <span className="material-symbols-outlined">biotech</span>
                      <strong>Order tests</strong>
                      <span>Select from available diagnostic tests</span>
                    </button>
                  </div>

                  {labSectionMode === "unset" && (
                    <p className="dp-lab-prompt">
                      <span className="material-symbols-outlined">touch_app</span>
                      Choose an option above to continue.
                    </p>
                  )}

                  {labSectionMode === "none" && (
                    <div className="dp-lab-confirmed-none">
                      <span className="material-symbols-outlined">info</span>
                      <p>No diagnostic tests for this visit. You can switch to <strong>Order tests</strong> anytime.</p>
                    </div>
                  )}

                  {labSectionMode === "pick" && (
                    <div className="dp-lab-pick-panel">
                      {selectedLabNames.length > 0 ? (
                        <p className="dp-lab-selected-summary">
                          <span className="material-symbols-outlined">check</span>
                          {selectedLabNames.length} selected: <strong>{selectedLabNames.join(", ")}</strong>
                        </p>
                      ) : (
                        <p className="dp-lab-selected-summary dp-lab-selected-summary--empty">
                          Tap tests below to add them to this visit.
                        </p>
                      )}

                      {ai && aiLabCodes.size > 0 && (
                        <div className="dp-lab-ai-bar">
                          <span>
                            <span className="material-symbols-outlined filled-icon">auto_awesome</span>
                            AI suggests {aiLabCodes.size} test{aiLabCodes.size > 1 ? "s" : ""} based on symptoms
                          </span>
                          <button type="button" className="dp-btn dp-btn--sm dp-btn--outline" onClick={addAllAiSuggestedLabs}>
                            Add AI suggestions
                          </button>
                        </div>
                      )}

                      {labCatalog.length === 0 ? (
                        <p className="dp-consult-lab-empty">Test catalog unavailable — refresh the page.</p>
                      ) : (
                        <div className="dp-consult-lab-chips">
                          {labCatalog.map((lab) => {
                            const checked = selectedLabs.has(lab.test_code);
                            const aiSuggested = aiLabCodes.has(lab.test_code);
                            return (
                              <label
                                key={lab.test_code}
                                className={`dp-consult-lab-chip${checked ? " dp-consult-lab-chip--on" : ""}${aiSuggested ? " dp-consult-lab-chip--ai" : ""}`}
                                title={lab.description ?? undefined}
                              >
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={(e) => {
                                    const next = new Set(selectedLabs);
                                    if (e.target.checked) next.add(lab.test_code);
                                    else next.delete(lab.test_code);
                                    setSelectedLabs(next);
                                    if (aiFilled.labs) setAiFilled((f) => ({ ...f, labs: false }));
                                  }}
                                />
                                <span className="material-symbols-outlined">biotech</span>
                                {lab.test_name}
                                {aiSuggested && !checked && <span className="dp-lab-ai-hint">AI</span>}
                              </label>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </section>

            {phase === "done" && (
              <div className="dp-consult-done-banner">
                <span className="material-symbols-outlined filled-icon">check_circle</span>
                <div>
                  <strong>Consultation completed</strong>
                  <p>Patient can view records in their health portal. Returning to visit records…</p>
                  <button
                    type="button"
                    className="dp-btn dp-btn--outline dp-btn--sm"
                    onClick={() => {
                      if (redirectTimerRef.current) clearTimeout(redirectTimerRef.current);
                      returnToPatientVisits(prep.patient.patient_id);
                    }}
                  >
                    Return to patient chart
                  </button>
                </div>
              </div>
            )}
          </div>

          {phase === "active" && (
            <div className="dp-consult-sticky-bar">
              <div className="dp-consult-sticky-inner">
                <div className="dp-consult-sticky-status">
                  {draftSaved && (
                    <span className="dp-consult-saved">
                      <span className="material-symbols-outlined">check_circle</span>
                      Draft saved
                    </span>
                  )}
                  <span className="dp-consult-sticky-hint">{progress}% complete</span>
                </div>
                <div className="dp-consult-sticky-actions">
                  {!aiApplied && (
                    <button type="button" className="dp-btn dp-btn--ai dp-btn--ghost-ai" disabled={aiLoading} onClick={generateAndFill}>
                      <span className="material-symbols-outlined">auto_awesome</span>
                      AI fill
                    </button>
                  )}
                  <button type="button" className="dp-btn dp-btn--outline" disabled={saving} onClick={saveDraft}>
                    Save draft
                  </button>
                  <button type="button" className="dp-btn dp-btn--primary" disabled={saving} onClick={completeConsultation}>
                    <span className="material-symbols-outlined">task_alt</span>
                    Complete consultation
                  </button>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {videoModal}
    </div>
  );
}
