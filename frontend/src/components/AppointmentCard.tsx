import { Link, useNavigate } from "react-router-dom";
import {
  appointmentDisplayId,
  buildCancelAppointmentMessage,
  buildRescheduleAppointmentMessage,
  type ChatNavigationState,
} from "../utils/appointmentChatActions";

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
  onJoinVideo?: (appointmentId: string) => void;
}

export default function AppointmentCard({
  appointment: a,
  showStatus = false,
  onJoinVideo,
}: Props) {
  const navigate = useNavigate();
  const { month, day } = apptDateParts(a.date);
  const normalizedStatus = a.status.toLowerCase();
  const isActive =
    normalizedStatus === "confirmed" ||
    normalizedStatus === "pending" ||
    normalizedStatus === "rescheduled";
  const isCompleted = normalizedStatus === "completed";
  const isCancelled = normalizedStatus === "cancelled" || normalizedStatus === "canceled";
  const isVideoConsultation =
    a.consultation_mode === "video" || Boolean(a.video_room_id);
  const videoCallAvailable =
    normalizedStatus === "confirmed" || normalizedStatus === "rescheduled";
  const statusLabel =
    normalizedStatus === "cancelled" || normalizedStatus === "canceled"
      ? "Cancelled"
      : normalizedStatus.charAt(0).toUpperCase() + normalizedStatus.slice(1);
  const aptId = appointmentDisplayId(a);

  function openChatWithAction(message: string) {
    navigate("/chat", { state: { pendingMessage: message } satisfies ChatNavigationState });
  }

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
            <span className={`pd-appt-status pd-appt-status--${normalizedStatus}`}>{statusLabel}</span>
          )}
        </div>
        <p className="pd-appt-meta">
          {a.apt_id ? <span className="pd-appt-id">{a.apt_id}</span> : null}
          Consultation · MediAI Clinic
        </p>
        <div className="pd-appt-tags">
          <span>
            <span className="material-symbols-outlined">schedule</span>
            {formatApptTime(a.time)}
          </span>
          <span>
            <span className="material-symbols-outlined">
              {isVideoConsultation ? "videocam" : videoCallAvailable ? "video_call" : "location_on"}
            </span>
            {isVideoConsultation
              ? "Video consultation"
              : videoCallAvailable
                ? "In-person · video available"
                : "In-person visit"}
          </span>
        </div>
      </div>

      <div className="pd-appt-actions">
        {isActive && (
          <>
            {videoCallAvailable ? (
              <button
                type="button"
                className="pd-appt-btn pd-appt-btn--video"
                onClick={() => onJoinVideo?.(a.id)}
              >
                Join Video
              </button>
            ) : (
              <button
                type="button"
                className="pd-appt-btn pd-appt-btn--video pd-appt-btn--disabled"
                disabled
                title="Video join is available for confirmed appointments"
              >
                Join Video
              </button>
            )}
            <button
              type="button"
              className="pd-appt-btn pd-appt-btn--reschedule"
              onClick={() => openChatWithAction(buildRescheduleAppointmentMessage(aptId))}
            >
              Reschedule
            </button>
            <button
              type="button"
              className="pd-appt-btn pd-appt-btn--cancel"
              onClick={() => openChatWithAction(buildCancelAppointmentMessage(aptId))}
            >
              Cancel
            </button>
          </>
        )}
        {isCompleted && (
          <Link to="/health-records" className="pd-appt-btn pd-appt-btn--reschedule">
            View records
          </Link>
        )}
        {isCancelled && (
          <span className="pd-muted">Cancelled by clinic</span>
        )}
      </div>
    </article>
  );
}
