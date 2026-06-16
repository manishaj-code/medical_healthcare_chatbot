import { Link } from "react-router-dom";
import {
  canStartConsultation,
  DoctorAppointment,
  formatDisplayDate,
  formatDoctorTime,
} from "../../utils/doctorPortal";

export interface AppointmentRow {
  appointment_id: string;
  patient_id?: string;
  patient_name?: string;
  date: string;
  time: string;
  status: string;
  consultation_mode?: string;
  is_video?: boolean;
  appointment_reason?: string | null;
  linked_report?: {
    report_id: string;
    filename: string;
    summary?: string;
    abnormal?: { test?: string; value?: string; flag?: string }[];
  } | null;
}

const STATUS_SECTIONS: {
  key: string;
  label: string;
  icon: string;
  tag: "success" | "info" | "warning" | "cancelled";
}[] = [
  { key: "confirmed", label: "Confirmed", icon: "check_circle", tag: "success" },
  { key: "pending", label: "Pending", icon: "hourglass_top", tag: "warning" },
  { key: "rescheduled", label: "Rescheduled", icon: "event_repeat", tag: "info" },
  { key: "completed", label: "Completed", icon: "task_alt", tag: "success" },
  { key: "cancelled", label: "Cancelled", icon: "cancel", tag: "cancelled" },
];

function statusTagClass(status: string): string {
  const s = status.toLowerCase();
  if (s === "confirmed" || s === "completed") return "success";
  if (s === "cancelled") return "cancelled";
  if (s === "pending") return "warning";
  return "info";
}

function formatStatusLabel(status: string): string {
  return status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
}

function sortAppointments(rows: AppointmentRow[]): AppointmentRow[] {
  return [...rows].sort((a, b) => {
    const da = `${a.date}T${a.time}`;
    const db = `${b.date}T${b.time}`;
    return db.localeCompare(da);
  });
}

export function groupAppointmentsByStatus<T extends AppointmentRow>(
  appointments: T[],
): { key: string; label: string; icon: string; tag: string; items: T[] }[] {
  const buckets = new Map<string, T[]>();
  for (const a of appointments) {
    const key = a.status.toLowerCase();
    const list = buckets.get(key) ?? [];
    list.push(a);
    buckets.set(key, list);
  }

  const ordered = STATUS_SECTIONS.filter((s) => buckets.has(s.key)).map((s) => ({
    ...s,
    items: sortAppointments(buckets.get(s.key)!),
  }));

  const known = new Set(STATUS_SECTIONS.map((s) => s.key));
  for (const [key, items] of buckets) {
    if (!known.has(key)) {
      ordered.push({
        key,
        label: formatStatusLabel(key),
        icon: "event",
        tag: "info",
        items: sortAppointments(items),
      });
    }
  }

  return ordered;
}

interface Props {
  appointments: AppointmentRow[];
  showPatient?: boolean;
  onViewPatient?: (patientId: string) => void;
}

export default function DoctorAppointmentsSections({ appointments, showPatient = true, onViewPatient }: Props) {
  const sections = groupAppointmentsByStatus(appointments);

  if (sections.length === 0) {
    return null;
  }

  return (
    <div className="dp-appt-sections">
      {sections.map((section) => (
        <section key={section.key} className="dp-appt-section">
          <header className="dp-appt-section-head">
            <div className="dp-appt-section-title">
              <span className="material-symbols-outlined">{section.icon}</span>
              <h3>{section.label}</h3>
              <span className={`dp-tag dp-tag--${section.tag}`}>{section.items.length}</span>
            </div>
          </header>
          <div className="dp-table-wrap">
            <table className="dp-table">
              <thead>
                <tr>
                  {showPatient && <th>Patient</th>}
                  <th>Date</th>
                  <th>Time</th>
                  <th>Status</th>
                  <th>Actions</th>
                  {onViewPatient && <th></th>}
                </tr>
              </thead>
              <tbody>
                {section.items.map((a) => (
                  <tr key={a.appointment_id}>
                    {showPatient && (
                      <td className="dp-table-patient">{a.patient_name ?? "—"}</td>
                    )}
                    <td>{formatDisplayDate(a.date)}</td>
                    <td>{formatDoctorTime(a.time)}</td>
                    <td>
                      <span className={`dp-tag dp-tag--${statusTagClass(a.status)}`}>
                        {formatStatusLabel(a.status)}
                      </span>
                      {a.appointment_reason ? (
                        <div className="dp-muted-note dp-appt-reason">{a.appointment_reason}</div>
                      ) : null}
                    </td>
                    <td>
                      {canStartConsultation(a.date, a.status) ? (
                        <Link
                          to={`/doctor/consultation/${a.appointment_id}`}
                          className="dp-btn dp-btn--primary dp-btn--sm"
                        >
                          Start consultation
                        </Link>
                      ) : (
                        <span className="dp-muted-note">—</span>
                      )}
                    </td>
                    {onViewPatient && a.patient_id && (
                      <td>
                        <button
                          type="button"
                          className="dp-btn dp-btn--primary dp-btn--sm"
                          onClick={() => onViewPatient(a.patient_id!)}
                        >
                          View
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}

export type { DoctorAppointment };
