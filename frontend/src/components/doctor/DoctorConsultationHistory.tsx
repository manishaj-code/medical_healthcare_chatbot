import { useMemo, useState } from "react";
import {
  formatDisplayDate,
  formatDoctorTime,
  isActiveAppointmentStatus,
  isOverdueAppointment,
  isUpcomingAppointment,
  patientInitials,
} from "../../utils/doctorPortal";
import { formatRiskLevelLabel, riskLevelCssVariant } from "../../utils/clinicalSummaryFormat";

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
  medications: { name: string; dosage?: string | null; frequency?: string | null }[];
  treatment_plan?: string | null;
  soap_assessment?: string | null;
  has_soap_note: boolean;
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
    return <p className="dp-consult-muted">Loading consultation history…</p>;
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
          {filtered.map((record) => {
            const overdue = recordIsOverdue(record);
            const busy = actionId === record.appointment_id;
            return (
              <article
                key={record.appointment_id}
                className={`dp-consult-history-card${overdue ? " dp-consult-history-card--overdue" : ""}`}
              >
                <div className="dp-consult-history-card-head">
                  <button
                    type="button"
                    className="dp-consult-patient-btn"
                    onClick={() => onOpenPatient(record.patient_id)}
                  >
                    <span className="dp-avatar dp-avatar--sm">{patientInitials(record.patient_name)}</span>
                    <span>
                      <strong>{record.patient_name}</strong>
                      <span className="dp-consult-apt">{record.apt_id}</span>
                    </span>
                  </button>
                  <div className="dp-consult-history-meta">
                    <span className="dp-consult-date">
                      {formatDisplayDate(record.date)} · {formatDoctorTime(record.time)}
                    </span>
                    <span className={`dp-visit-status dp-visit-status--${statusTone(record)}`}>
                      {statusLabel(record)}
                    </span>
                  </div>
                </div>

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
                      Medications
                    </h4>
                    {record.medications.length > 0 ? (
                      <ul className="dp-consult-med-list">
                        {record.medications.map((m) => (
                          <li key={m.name}>
                            <strong>{m.name}</strong>
                            <span>
                              {[m.dosage, m.frequency].filter(Boolean).join(" · ") || "Active on profile"}
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="dp-consult-muted">No medications on patient profile</p>
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

                {record.summary_excerpt && (
                  <p className="dp-consult-summary">
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
                        onClick={() => void runAction(record.appointment_id, "complete")}
                      >
                        {busy ? "Saving…" : "Mark completed"}
                      </button>
                      <button
                        type="button"
                        className="dp-btn dp-btn--ghost dp-btn--sm"
                        disabled={busy}
                        onClick={() => void runAction(record.appointment_id, "cancel")}
                      >
                        Mark cancelled
                      </button>
                    </>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
