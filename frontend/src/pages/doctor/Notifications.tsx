import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { NotificationItem, typeIcon, typeLabel } from "../../utils/notifications";

export default function DoctorNotifications() {
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const notes = await api<NotificationItem[]>("/api/v1/doctor/notifications");
      setNotifications(notes);
      await api("/api/v1/doctor/notifications/mark-read", {
        method: "POST",
        body: JSON.stringify({ ids: null }),
      });
    } catch {
      setNotifications([]);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="dp-page">
      <div className="dp-page-head">
        <div>
          <Link to="/doctor" className="dp-back-link">
            <span className="material-symbols-outlined">arrow_back</span>
            Back to dashboard
          </Link>
          <h1 className="dp-page-title">Notifications</h1>
          <p className="dp-page-sub">Appointment updates, refill requests, and clinical alerts.</p>
        </div>
        <button type="button" className="dp-btn dp-btn--outline" onClick={() => void load()} disabled={loading}>
          Refresh
        </button>
      </div>

      <div className="dp-card dp-notifications-card">
        {loading && <p className="dp-muted">Loading notifications...</p>}
        {!loading && notifications.length === 0 && (
          <p className="dp-muted">No notifications yet.</p>
        )}
        {!loading && notifications.length > 0 && (
          <ul className="pd-notification-list">
            {notifications.map((n) => (
              <li
                key={n.id}
                className={`pd-notification-card pd-notification-card--${n.type.replace(/_/g, "-")}${n.is_read ? "" : " pd-notification-card--unread"}`}
              >
                <div className="pd-notification-card-head">
                  <span className="material-symbols-outlined pd-notification-icon">{typeIcon(n.type)}</span>
                  <span className="pd-notification-type">{typeLabel(n.type)}</span>
                  <time className="pd-notification-time">
                    {n.sent_at ? new Date(n.sent_at).toLocaleString() : ""}
                  </time>
                </div>
                <p className="pd-notification-message">{n.message}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
