import { Link } from "react-router-dom";
import { formatDisplayDate } from "../../utils/doctorPortal";

export interface MedicationSourceVisit {
  appointment_id: string;
  apt_id: string;
  visit_date: string;
  chief_complaint?: string | null;
  diagnosis?: string | null;
  appointment_reason?: string | null;
}

export interface MedicationTimelineEntry {
  id: string;
  medication_id?: string | null;
  name: string;
  dosage?: string | null;
  frequency?: string | null;
  duration?: string | null;
  instructions?: string | null;
  prescribed_at: string;
  course_end_date?: string | null;
  days_since_prescribed: number;
  is_active: boolean;
  continuation_status: "continue" | "refill_suggested" | "course_ended";
  refill_suggested: boolean;
  pending_refill: boolean;
  source: MedicationSourceVisit;
}

export interface MedicationTimelinePayload {
  medications: MedicationTimelineEntry[];
  active_medications: MedicationTimelineEntry[];
  ended_medications: MedicationTimelineEntry[];
  pending_refills: {
    id: string;
    medication_name: string;
    medication_dosage?: string | null;
    medication_frequency?: string | null;
    requested_at?: string | null;
  }[];
  summary: {
    total_prescribed: number;
    active_count: number;
    ended_count: number;
    pending_refill_count: number;
  };
}

function sourceContext(source: MedicationSourceVisit): string {
  return (
    source.appointment_reason?.trim() ||
    source.chief_complaint?.trim() ||
    source.diagnosis?.trim() ||
    "General consultation"
  );
}

function statusLabel(entry: MedicationTimelineEntry): { text: string; tone: string } {
  if (entry.pending_refill) return { text: "Refill requested", tone: "warning" };
  if (entry.continuation_status === "refill_suggested") {
    return { text: "Refill suggested", tone: "info" };
  }
  if (entry.continuation_status === "continue") {
    return { text: "Continue", tone: "success" };
  }
  return { text: "Course ended", tone: "muted" };
}

function MedicationRow({
  entry,
  onViewVisit,
}: {
  entry: MedicationTimelineEntry;
  onViewVisit?: (appointmentId: string) => void;
}) {
  const badge = statusLabel(entry);
  const detail = [entry.dosage, entry.frequency].filter(Boolean).join(" · ");
  const durationText = entry.duration ? ` · ${entry.duration}` : "";

  return (
    <li className="dp-med-timeline-item">
      <span className="dp-visit-med-icon material-symbols-outlined">medication</span>
      <div className="dp-med-timeline-body">
        <div className="dp-med-timeline-top">
          <strong>{entry.name}</strong>
          <span className={`dp-med-status dp-med-status--${badge.tone}`}>{badge.text}</span>
        </div>
        <p className="dp-med-timeline-dose">
          {detail || "Prescribed"}
          {durationText}
        </p>
        <p className="dp-med-timeline-source">
          From{" "}
          {onViewVisit ? (
            <button
              type="button"
              className="dp-link dp-med-timeline-link"
              onClick={() => onViewVisit(entry.source.appointment_id)}
            >
              {entry.source.apt_id}
            </button>
          ) : (
            <span>{entry.source.apt_id}</span>
          )}{" "}
          · {formatDisplayDate(entry.source.visit_date)} · {sourceContext(entry.source)}
        </p>
        {entry.course_end_date && entry.continuation_status === "refill_suggested" && (
          <p className="dp-muted-note dp-med-timeline-meta">
            Course ended {formatDisplayDate(entry.course_end_date)} — still active on file
          </p>
        )}
        {entry.continuation_status === "continue" && entry.days_since_prescribed > 30 && (
          <p className="dp-muted-note dp-med-timeline-meta">
            Ongoing — review at this visit ({entry.days_since_prescribed} days since prescribed)
          </p>
        )}
      </div>
    </li>
  );
}

interface Props {
  timeline: MedicationTimelinePayload;
  onViewVisit?: (appointmentId: string) => void;
  onOpenRefills?: () => void;
}

export default function DoctorMedicationTimeline({ timeline, onViewVisit, onOpenRefills }: Props) {
  const { summary, active_medications, ended_medications, pending_refills } = timeline;

  if (summary.total_prescribed === 0 && pending_refills.length === 0) {
    return null;
  }

  return (
    <div className="dp-med-timeline">
      {pending_refills.length > 0 && (
        <div className="dp-med-timeline-alert">
          <span className="material-symbols-outlined">notifications</span>
          <div>
            <strong>
              {pending_refills.length} pending refill request{pending_refills.length !== 1 ? "s" : ""}
            </strong>
            <p className="dp-muted-note" style={{ margin: "4px 0 0" }}>
              {pending_refills.map((r) => r.medication_name).join(", ")}
            </p>
          </div>
          {onOpenRefills && (
            <button type="button" className="dp-btn dp-btn--ghost dp-btn--sm" onClick={onOpenRefills}>
              Review
            </button>
          )}
        </div>
      )}

      {active_medications.length > 0 && (
        <section className="dp-med-timeline-section">
          <h4>
            <span className="material-symbols-outlined">medication</span>
            Current medications
            <span className="dp-visit-section-count">{active_medications.length}</span>
          </h4>
          <p className="dp-med-timeline-hint">
            Review what to continue or refill at this visit. Each item links to the prescribing visit.
          </p>
          <ul className="dp-visit-med-list">
            {active_medications.map((entry) => (
              <MedicationRow key={entry.id} entry={entry} onViewVisit={onViewVisit} />
            ))}
          </ul>
        </section>
      )}

      {ended_medications.length > 0 && (
        <section className="dp-med-timeline-section dp-med-timeline-section--muted">
          <h4>
            <span className="material-symbols-outlined">history</span>
            Past courses
            <span className="dp-visit-section-count">{ended_medications.length}</span>
          </h4>
          <ul className="dp-visit-med-list">
            {ended_medications.map((entry) => (
              <MedicationRow key={`ended-${entry.id}`} entry={entry} onViewVisit={onViewVisit} />
            ))}
          </ul>
        </section>
      )}

      {summary.total_prescribed === 0 && pending_refills.length > 0 && onOpenRefills && (
        <Link to="/doctor" state={{ tab: "refills" }} className="dp-link">
          Open refill queue →
        </Link>
      )}
    </div>
  );
}
