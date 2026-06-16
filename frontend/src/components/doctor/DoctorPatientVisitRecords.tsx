import { useState, type ReactNode } from "react";
import {
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

export interface VisitRecord {
  appointment_id: string;
  apt_id: string;
  date: string;
  time: string;
  status: string;
  completed_at?: string | null;
  consultation_mode: string;
  is_video: boolean;
  summary?: string | null;
  soap_note?: VisitSoapNote | null;
  assessment?: VisitAssessment | null;
}

export interface VisitRecordsPayload {
  visits: VisitRecord[];
  medications: { name: string; dosage?: string | null; frequency?: string | null }[];
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
  if (visit.is_video) return "videocam";
  if (visit.status === "completed") return "task_alt";
  if (visit.status === "cancelled") return "event_busy";
  return "calendar_month";
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

function VisitCard({
  visit,
  defaultOpen,
  onMarkCompleted,
  onMarkCancelled,
}: {
  visit: VisitRecord;
  defaultOpen?: boolean;
  onMarkCompleted?: (appointmentId: string) => Promise<void>;
  onMarkCancelled?: (appointmentId: string) => Promise<void>;
}) {
  const [open, setOpen] = useState(defaultOpen ?? visit.status === "completed");
  const [busy, setBusy] = useState(false);
  const overdue = isOverdueAppointment(visit.date, visit.time, visit.status);
  const risk = visit.assessment?.risk_level;
  const symptoms = visit.assessment?.symptoms ?? [];
  const hasDetails =
    symptoms.length > 0 ||
    (visit.summary && !/no (ai )?summary yet/i.test(visit.summary)) ||
    Boolean(visit.soap_note);

  return (
    <article
      className={`dp-visit-card dp-visit-card--${visit.status}${open ? " dp-visit-card--open" : ""}${
        visit.is_video ? " dp-visit-card--video" : ""
      }${overdue ? " dp-visit-card--overdue" : ""}`}
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
            {visit.is_video && (
              <span className="dp-visit-mode">
                <span className="material-symbols-outlined">videocam</span>
                Video consult
              </span>
            )}
            {!visit.is_video && visit.consultation_mode !== "in_person" && (
              <span className="dp-visit-mode">{visit.consultation_mode}</span>
            )}
          </div>
          {!open && symptoms.length > 0 && (
            <div className="dp-visit-preview-chips">
              {symptoms.slice(0, 3).map((s) => (
                <span key={s} className="dp-visit-preview-chip">
                  {s}
                </span>
              ))}
              {symptoms.length > 3 && (
                <span className="dp-visit-preview-chip dp-visit-preview-chip--more">
                  +{symptoms.length - 3}
                </span>
              )}
            </div>
          )}
        </div>

        <span className={`material-symbols-outlined dp-visit-chevron${open ? " dp-visit-chevron--open" : ""}`}>
          expand_more
        </span>
      </button>

      {open && (
        <div className="dp-visit-card-body">
          {!hasDetails && visit.status !== "completed" && (
            <div className="dp-visit-pending-note">
              <span className="material-symbols-outlined">info</span>
              <p>
                Triage summary and clinical notes will appear here after the patient completes
                pre-visit assessment or after you document the consultation.
              </p>
            </div>
          )}

          {symptoms.length > 0 && (
            <section className="dp-visit-block">
              <div className="dp-visit-block-head">
                <span className="material-symbols-outlined">healing</span>
                <h4>Symptoms &amp; triage</h4>
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

          {visit.summary && !/no (ai )?summary yet/i.test(visit.summary) && (
            <VisitAiSummary summary={visit.summary} hasTriageBlock={symptoms.length > 0} />
          )}

          {visit.soap_note && (
            <section className="dp-visit-block">
              <div className="dp-visit-block-head">
                <span className="material-symbols-outlined">clinical_notes</span>
                <h4>Doctor notes (SOAP)</h4>
              </div>
              <div className="dp-visit-soap-grid">
                {visit.soap_note.subjective && (
                  <div className="dp-visit-soap-item">
                    <span>S</span>
                    <div>
                      <strong>Subjective</strong>
                      <p>{visit.soap_note.subjective}</p>
                    </div>
                  </div>
                )}
                {visit.soap_note.objective && (
                  <div className="dp-visit-soap-item">
                    <span>O</span>
                    <div>
                      <strong>Objective</strong>
                      <p>{visit.soap_note.objective}</p>
                    </div>
                  </div>
                )}
                {visit.soap_note.assessment && (
                  <div className="dp-visit-soap-item">
                    <span>A</span>
                    <div>
                      <strong>Assessment</strong>
                      <p>{visit.soap_note.assessment}</p>
                    </div>
                  </div>
                )}
                {visit.soap_note.plan && (
                  <div className="dp-visit-soap-item">
                    <span>P</span>
                    <div>
                      <strong>Plan</strong>
                      <p>{visit.soap_note.plan}</p>
                    </div>
                  </div>
                )}
              </div>
            </section>
          )}

          {visit.status === "completed" && !visit.soap_note && !visit.summary && symptoms.length === 0 && (
            <p className="dp-visit-empty-detail">No structured notes captured for this visit yet.</p>
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
}: {
  data: VisitRecordsPayload;
  onMarkCompleted?: (appointmentId: string) => Promise<void>;
  onMarkCancelled?: (appointmentId: string) => Promise<void>;
}) {
  const completed = data.visits.filter((v) => v.status === "completed");
  const upcoming = data.visits.filter((v) => isUpcomingAppointment(v.date, v.time, v.status));
  const overdue = data.visits.filter((v) => isOverdueAppointment(v.date, v.time, v.status));
  const cancelled = data.visits.filter((v) => v.status === "cancelled");

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
                <h3>Past due — needs status</h3>
                <span className="dp-visit-section-count">{overdue.length}</span>
              </header>
              <div className="dp-visit-group-body">
                <div className="dp-visit-timeline">
                  {overdue.map((visit) => (
                    <VisitCard
                      key={visit.appointment_id}
                      visit={visit}
                      defaultOpen
                      onMarkCompleted={onMarkCompleted}
                      onMarkCancelled={onMarkCancelled}
                    />
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
                    <VisitCard key={visit.appointment_id} visit={visit} defaultOpen />
                  ))}
                </div>
              </div>
            </section>
          )}

          {completed.length > 0 && (
            <section className="dp-visit-group-card">
              <header className="dp-visit-section-head">
                <span className="material-symbols-outlined">history</span>
                <h3>Past consultations</h3>
                <span className="dp-visit-section-count">{completed.length}</span>
              </header>
              <div className="dp-visit-group-body">
                <div className="dp-visit-timeline">
                  {completed.map((visit) => (
                    <VisitCard key={visit.appointment_id} visit={visit} />
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
                    <VisitCard key={visit.appointment_id} visit={visit} />
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
            title="Medications"
            count={data.medications.length}
            emptyIcon="medication"
            emptyText="No medications on file for this patient."
          >
            {data.medications.length > 0 ? (
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
