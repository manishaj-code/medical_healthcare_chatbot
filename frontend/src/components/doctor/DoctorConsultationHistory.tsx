import { useMemo, useState } from "react";
import {
  consultationModeLabel,
  formatDisplayDate,
  formatDoctorTime,
  isActiveAppointmentStatus,
  isOverdueAppointment,
  isUpcomingAppointment,
  patientInitials,
} from "../../utils/doctorPortal";
import { formatRiskLevelLabel, riskLevelCssVariant } from "../../utils/clinicalSummaryFormat";
import { ConsultationHistorySkeleton } from "../../components/skeleton";

export interface ConsultationHistoryRecord {
  appointment_id: string;
  apt_id: string;
  patient_id: string;
  patient_name: string;
  date: string;
  time: string;
  status: string;
  is_past?: boolean;
  is_overdue?: boolean;
  completed_at?: string | null;
  consultation_mode: string;
  is_video: boolean;
  symptoms: string[];
  risk_level?: string | null;
  recommended_specialty?: string | null;
  duration?: string | null;
  medications: { name: string; dosage?: string | null; frequency?: string | null; duration?: string | null }[];
  appointment_reason?: string | null;
  treatment_plan?: string | null;
  soap_assessment?: string | null;
  has_soap_note: boolean;
  follow_up_date?: string | null;
  summary_excerpt?: string | null;
}

interface Props {
  records: ConsultationHistoryRecord[];
  loading?: boolean;
  onOpenPatient: (patientId: string) => void;
  onMarkCompleted?: (appointmentId: string) => Promise<void>;
  onMarkCancelled?: (appointmentId: string) => Promise<void>;
}

type StatusFilter = "all" | "upcoming" | "overdue" | "completed" | "cancelled";

function recordIsOverdue(record: ConsultationHistoryRecord): boolean {
  if (!isActiveAppointmentStatus(record.status)) return false;
  if (record.is_overdue != null) return record.is_overdue;
  return isOverdueAppointment(record.date, record.time, record.status);
}

function recordIsUpcoming(record: ConsultationHistoryRecord): boolean {
  return isUpcomingAppointment(record.date, record.time, record.status);
}

function statusLabel(record: ConsultationHistoryRecord): string {
  if (recordIsOverdue(record)) return "Past due";
  const s = record.status.toLowerCase();
  if (s === "confirmed") return "Confirmed";
  if (s === "completed") return "Completed";
  if (s === "pending") return "Pending";
  if (s === "cancelled") return "Cancelled";
  return record.status.charAt(0).toUpperCase() + record.status.slice(1).toLowerCase();
}

function statusTone(record: ConsultationHistoryRecord): string {
  if (recordIsOverdue(record)) return "warning";
  const s = record.status.toLowerCase();
  if (s === "completed" || s === "confirmed") return "success";
  if (s === "cancelled") return "cancelled";
  if (s === "pending") return "warning";
  return "info";
}

function matchesFilter(record: ConsultationHistoryRecord, filter: StatusFilter): boolean {
  const s = record.status.toLowerCase();
  if (filter === "all") return true;
  if (filter === "completed") return s === "completed";
  if (filter === "cancelled") return s === "cancelled";
  if (filter === "upcoming") return recordIsUpcoming(record);
  if (filter === "overdue") return recordIsOverdue(record);
  return false;
}

function collapseSnippet(record: ConsultationHistoryRecord): string {
  const parts: string[] = [];
  if (record.appointment_reason) parts.push(record.appointment_reason);
  if (record.symptoms.length) parts.push(record.symptoms.slice(0, 3).join(", "));
  if (record.medications.length) {
    parts.push(
      `Rx: ${record.medications
        .slice(0, 2)
        .map((m) => m.name)
        .join(", ")}${record.medications.length > 2 ? "…" : ""}`,
    );
  }
  if (record.soap_assessment) parts.push(record.soap_assessment);
  else if (record.treatment_plan) {
    const line = record.treatment_plan.split("\n")[0]?.trim();
    if (line) parts.push(line.replace(/^\d+\.\s*/, ""));
  }
  if (record.follow_up_date) parts.push(`Follow-up ${formatDisplayDate(record.follow_up_date)}`);
  return parts.join(" · ");
}

function ConsultationHistoryCard({
  record,
  busy,
  onOpenPatient,
  onMarkCompleted,
  onMarkCancelled,
  onAction,
}: {
  record: ConsultationHistoryRecord;
  busy: boolean;
  onOpenPatient: (patientId: string) => void;
  onMarkCompleted?: (appointmentId: string) => Promise<void>;
  onMarkCancelled?: (appointmentId: string) => Promise<void>;
  onAction: (appointmentId: string, action: "complete" | "cancel") => void;
}) {
  const [open, setOpen] = useState(false);
  const overdue = recordIsOverdue(record);
  const snippet = collapseSnippet(record);
  const hasExpandableContent =
    record.symptoms.length > 0 ||
    record.medications.length > 0 ||
    Boolean(record.treatment_plan) ||
    Boolean(record.soap_assessment) ||
    Boolean(record.summary_excerpt) ||
    Boolean(record.follow_up_date) ||
    Boolean(record.duration || record.risk_level || record.recommended_specialty);

  return (
    <article
      className={`dp-consult-history-card${open ? " dp-consult-history-card--open" : ""}${
        overdue ? " dp-consult-history-card--overdue" : ""
      }`}
    >
      <div className="dp-consult-history-card-head">
        <button
          type="button"
          className="dp-consult-patient-btn"
          onClick={() => onOpenPatient(record.patient_id)}
          title="Open patient chart"
        >
          <span className="dp-avatar dp-avatar--sm">{patientInitials(record.patient_name)}</span>
          <span className="dp-consult-patient-text">
            <strong>{record.patient_name}</strong>
            <span className="dp-consult-apt">{record.apt_id}</span>
          </span>
        </button>

        {hasExpandableContent ? (
          <button
            type="button"
            className="dp-consult-history-expand"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-label={open ? "Hide visit details" : "Show visit details"}
          >
            {!open && (
              <span className="dp-consult-history-snippet" title={snippet || "View visit details"}>
                {snippet || "View details"}
              </span>
            )}
            <span className="dp-consult-history-expand-trail">
              <span className="dp-consult-history-meta">
                <span className="dp-consult-date">
                  {formatDisplayDate(record.date)} · {formatDoctorTime(record.time)}
                </span>
                <span className="dp-consult-mode-pill">
                  {consultationModeLabel(record.consultation_mode, record.is_video)}
                </span>
                <span className={`dp-visit-status dp-visit-status--${statusTone(record)}`}>
                  {statusLabel(record)}
                </span>
              </span>
              <span
                className={`material-symbols-outlined dp-consult-history-chevron${open ? " dp-consult-history-chevron--open" : ""}`}
                aria-hidden
              >
                expand_more
              </span>
            </span>
          </button>
        ) : (
          <div className="dp-consult-history-meta dp-consult-history-meta--static">
            <span className="dp-consult-date">
              {formatDisplayDate(record.date)} · {formatDoctorTime(record.time)}
            </span>
            <span className={`dp-visit-status dp-visit-status--${statusTone(record)}`}>
              {statusLabel(record)}
            </span>
          </div>
        )}
      </div>

      {open && (
        <>
          <div className="dp-consult-history-card-body">
            <div className="dp-consult-history-col">
              <h4>
                <span className="material-symbols-outlined">healing</span>
                Symptoms
              </h4>
              {record.symptoms.length > 0 ? (
                <div className="dp-visit-chips">
                  {record.symptoms.map((s) => (
                    <span key={s} className="dp-visit-chip">
                      {s}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="dp-consult-muted">No triage symptoms recorded</p>
              )}
              {(record.duration || record.risk_level || record.recommended_specialty) && (
                <div className="dp-visit-meta-row">
                  {record.duration && (
                    <span className="dp-visit-meta-pill">
                      <span className="material-symbols-outlined">schedule</span>
                      {record.duration}
                    </span>
                  )}
                  {record.risk_level && (
                    <span
                      className={`dp-clinical-risk-badge dp-clinical-risk-badge--${riskLevelCssVariant(record.risk_level)}`}
                    >
                      {formatRiskLevelLabel(record.risk_level)}
                    </span>
                  )}
                  {record.recommended_specialty && (
                    <span className="dp-visit-meta-pill">
                      <span className="material-symbols-outlined">medical_services</span>
                      {record.recommended_specialty}
                    </span>
                  )}
                </div>
              )}
            </div>

            <div className="dp-consult-history-col">
              <h4>
                <span className="material-symbols-outlined">medication</span>
                Prescribed this visit
              </h4>
              {record.medications.length > 0 ? (
                <ul className="dp-consult-med-list">
                  {record.medications.map((m) => (
                    <li key={`${m.name}-${m.dosage ?? ""}-${m.frequency ?? ""}`}>
                      <strong>{m.name}</strong>
                      <span>
                        {[m.dosage, m.frequency, m.duration].filter(Boolean).join(" · ")}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="dp-consult-muted">No prescriptions recorded for this appointment</p>
              )}
              {record.treatment_plan && (
                <div className="dp-consult-plan">
                  <span className="dp-consult-plan-label">Treatment plan</span>
                  <p>{record.treatment_plan}</p>
                </div>
              )}
              {record.soap_assessment && (
                <div className="dp-consult-plan">
                  <span className="dp-consult-plan-label">Clinical assessment</span>
                  <p>{record.soap_assessment}</p>
                </div>
              )}
            </div>
          </div>

          {record.follow_up_date && (
            <div className="dp-visit-followup">
              <span className="material-symbols-outlined">event</span>
              <span>
                Follow-up scheduled for <strong>{formatDisplayDate(record.follow_up_date)}</strong>
              </span>
            </div>
          )}

          {record.summary_excerpt && (
            <p className="dp-consult-summary-excerpt">
              <span className="material-symbols-outlined">auto_awesome</span>
              {record.summary_excerpt}
            </p>
          )}

          <div className="dp-consult-history-card-foot">
            <button
              type="button"
              className="dp-btn dp-btn--outline dp-btn--sm"
              onClick={() => onOpenPatient(record.patient_id)}
            >
              Open patient chart
            </button>
            {overdue && onMarkCompleted && onMarkCancelled && (
              <>
                <button
                  type="button"
                  className="dp-btn dp-btn--primary dp-btn--sm"
                  disabled={busy}
                  onClick={() => onAction(record.appointment_id, "complete")}
                >
                  {busy ? "Saving…" : "Mark completed"}
                </button>
                <button
                  type="button"
                  className="dp-btn dp-btn--ghost dp-btn--sm"
                  disabled={busy}
                  onClick={() => onAction(record.appointment_id, "cancel")}
                >
                  Mark cancelled
                </button>
              </>
            )}
          </div>
        </>
      )}
    </article>
  );
}

export default function DoctorConsultationHistory({
  records,
  loading,
  onOpenPatient,
  onMarkCompleted,
  onMarkCancelled,
}: Props) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [actionId, setActionId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return records.filter((r) => {
      if (!matchesFilter(r, statusFilter)) return false;
      if (!q) return true;
      const haystack = [
        r.patient_name,
        r.apt_id,
        r.symptoms.join(" "),
        r.recommended_specialty || "",
        r.treatment_plan || "",
        r.summary_excerpt || "",
        ...r.medications.map((m) => m.name),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [records, statusFilter, query]);

  const counts = useMemo(
    () => ({
      all: records.length,
      upcoming: records.filter((r) => recordIsUpcoming(r)).length,
      overdue: records.filter((r) => recordIsOverdue(r)).length,
      completed: records.filter((r) => r.status.toLowerCase() === "completed").length,
      cancelled: records.filter((r) => r.status.toLowerCase() === "cancelled").length,
    }),
    [records],
  );

  const runAction = async (appointmentId: string, action: "complete" | "cancel") => {
    setActionId(appointmentId);
    setActionError(null);
    try {
      if (action === "complete" && onMarkCompleted) await onMarkCompleted(appointmentId);
      if (action === "cancel" && onMarkCancelled) await onMarkCancelled(appointmentId);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not update appointment status.";
      setActionError(message);
    } finally {
      setActionId(null);
    }
  };

  if (loading) {
    return <ConsultationHistorySkeleton count={5} />;
  }

  return (
    <div className="dp-consult-history">
      {actionError && (
        <div className="dp-consult-action-error" role="alert">
          <span className="material-symbols-outlined">error</span>
          <p>{actionError}</p>
          <button type="button" className="dp-btn dp-btn--ghost dp-btn--sm" onClick={() => setActionError(null)}>
            Dismiss
          </button>
        </div>
      )}
      {counts.overdue > 0 && (
        <div className="dp-consult-overdue-banner" role="status">
          <span className="material-symbols-outlined">schedule</span>
          <p>
            <strong>{counts.overdue} past-due visit{counts.overdue !== 1 ? "s" : ""}</strong> still marked as
            confirmed. Mark each as completed after the consult or cancelled if the patient did not attend.
          </p>
          <button type="button" className="dp-btn dp-btn--outline dp-btn--sm" onClick={() => setStatusFilter("overdue")}>
            Review
          </button>
        </div>
      )}

      <div className="dp-consult-history-toolbar">
        <div className="dp-consult-history-filters" role="tablist" aria-label="Filter by status">
          {(
            [
              ["all", "All visits"],
              ["upcoming", "Upcoming"],
              ["overdue", "Past due"],
              ["completed", "Completed"],
              ["cancelled", "Cancelled"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              role="tab"
              aria-selected={statusFilter === id}
              className={`dp-consult-filter${statusFilter === id ? " dp-consult-filter--active" : ""}${
                id === "overdue" && counts.overdue > 0 ? " dp-consult-filter--alert" : ""
              }`}
              onClick={() => setStatusFilter(id)}
            >
              {label}
              <span className="dp-consult-filter-count">{counts[id]}</span>
            </button>
          ))}
        </div>
        <div className="dp-consult-history-search">
          <span className="material-symbols-outlined">search</span>
          <input
            type="search"
            placeholder="Search patient, symptoms, medications…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search consultation history"
          />
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="dp-consult-history-empty">
          <span className="material-symbols-outlined">history</span>
          <strong>No matching visits</strong>
          <p>
            {records.length === 0
              ? "When patients book and consult with you, their visit history will appear here."
              : "Try a different filter or search term."}
          </p>
        </div>
      ) : (
        <div className="dp-consult-history-list">
          {filtered.map((record) => (
            <ConsultationHistoryCard
              key={record.appointment_id}
              record={record}
              busy={actionId === record.appointment_id}
              onOpenPatient={onOpenPatient}
              onMarkCompleted={onMarkCompleted}
              onMarkCancelled={onMarkCancelled}
              onAction={(id, action) => void runAction(id, action)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
