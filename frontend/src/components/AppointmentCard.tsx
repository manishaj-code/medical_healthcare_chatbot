import { Link } from "react-router-dom";

export interface AppointmentItem {
  id: string;
  doctor_name?: string;
  date: string;
  time: string;
  status: string;
  consultation_mode?: string;
  video_room_id?: string | null;
  apt_id?: string;
}

export function formatApptTime(t: string): string {
  const parts = t.split(":");
  if (parts.length < 2) return t;
  const h = parseInt(parts[0], 10);
  const m = parts[1].slice(0, 2);
  const ampm = h >= 12 ? "PM" : "AM";
  return `${h % 12 || 12}:${m} ${ampm}`;
}

export function apptDateParts(dateStr: string): { month: string; day: string } {
  const d = new Date(`${dateStr}T12:00:00`);
  return {
    month: d.toLocaleDateString("en-US", { month: "short" }).toUpperCase(),
    day: String(d.getDate()),
  };
}

interface Props {
  appointment: AppointmentItem;
  showStatus?: boolean;
  onCancel?: (id: string) => void;
  cancelling?: boolean;
}

export default function AppointmentCard({
  appointment: a,
  showStatus = false,
  onCancel,
  cancelling = false,
}: Props) {
  const { month, day } = apptDateParts(a.date);
  const isConfirmed = a.status === "confirmed";
  const isVideoConsultation = a.consultation_mode === "video";
  const statusLabel = a.status.charAt(0).toUpperCase() + a.status.slice(1);

  return (
    <article className="pd-appt-card">
      <div className="pd-appt-date">
        <span>{month}</span>
        <strong>{day}</strong>
      </div>

      <div className="pd-appt-info">
        <div className="pd-appt-title-row">
          <p className="pd-appt-doctor">{a.doctor_name || "Doctor"}</p>
          {showStatus && (
            <span className={`pd-appt-status pd-appt-status--${a.status}`}>{statusLabel}</span>
          )}
        </div>
        <p className="pd-appt-meta">Consultation · MediAI Clinic</p>
        <div className="pd-appt-tags">
          <span>
            <span className="material-symbols-outlined">schedule</span>
            {formatApptTime(a.time)}
          </span>
          <span>
            <span className="material-symbols-outlined">
              {isVideoConsultation ? "videocam" : "location_on"}
            </span>
            {isVideoConsultation ? "Video consultation" : "In-person visit"}
          </span>
        </div>
      </div>

      <div className="pd-appt-actions">
        {isConfirmed && (
          <>
            {isVideoConsultation ? (
              <Link
                to={`/video/${a.id}`}
                className="pd-appt-btn pd-appt-btn--video"
              >
                Join Video
              </Link>
            ) : (
              <button
                type="button"
                className="pd-appt-btn pd-appt-btn--video pd-appt-btn--disabled"
                disabled
                title="Online consultation has not been approved for this appointment"
              >
                Join Video
              </button>
            )}
            <Link to="/chat" className="pd-appt-btn pd-appt-btn--reschedule">
              Reschedule
            </Link>
            {onCancel && (
              <button
                type="button"
                className="pd-appt-btn pd-appt-btn--cancel"
                disabled={cancelling}
                onClick={() => onCancel(a.id)}
              >
                {cancelling ? "Cancelling..." : "Cancel"}
              </button>
            )}
          </>
        )}
      </div>
    </article>
  );
}
