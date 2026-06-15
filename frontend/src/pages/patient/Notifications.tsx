import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { NotificationItem, typeIcon, typeLabel } from "../../utils/notifications";

interface RefillRequest {
  id: string;
  medication_name: string;
  medication_dosage: string | null;
  status: string;
  doctor_name: string;
  denial_reason: string | null;
  requested_at: string | null;
  reviewed_at: string | null;
}

function statusClass(status: string): string {
  if (status === "approved") return "pd-refill-status pd-refill-status--approved";
  if (status === "denied") return "pd-refill-status pd-refill-status--denied";
  return "pd-refill-status pd-refill-status--pending";
}

export default function PatientNotifications() {
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [refills, setRefills] = useState<RefillRequest[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [notes, refillRows] = await Promise.all([
        api<NotificationItem[]>("/api/v1/patients/me/notifications"),
        api<RefillRequest[]>("/api/v1/patients/me/refill-requests"),
      ]);
      setNotifications(notes);
      setRefills(refillRows);
      await api("/api/v1/patients/me/notifications/mark-read", {
        method: "POST",
        body: JSON.stringify({ ids: null }),
      });
    } catch {
      setNotifications([]);
      setRefills([]);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="patient-dashboard">
      <section className="pd-section pd-notifications-page">
        <div className="pd-section-head pd-notifications-head">
          <div>
            <h3>Notifications & Refills</h3>
            <p className="pd-section-sub">
              Prescription refill status and updates from your care team.
            </p>
          </div>
          <div className="pd-notifications-actions">
            <button type="button" className="pd-outline-btn" onClick={() => void load()} disabled={loading}>
              Refresh
            </button>
            <Link to="/chat" className="pd-cta-btn pd-cta-btn--compact">
              <span className="material-symbols-outlined">smart_toy</span>
              Request refill in chat
            </Link>
          </div>
        </div>

        <div className="pd-notifications-grid">
          <div className="pd-notifications-panel">
            <h4 className="pd-notifications-panel-title">Prescription refill requests</h4>
            {loading && <p className="pd-muted">Loading refill requests...</p>}
            {!loading && refills.length === 0 && (
              <div className="pd-empty-card pd-notifications-empty">
                <span className="material-symbols-outlined pd-empty-icon">medication</span>
                <p>No refill requests yet.</p>
                <p className="pd-muted">Open AI Consultation and ask for a prescription refill.</p>
                <Link to="/chat" className="pd-outline-btn">Go to chat</Link>
              </div>
            )}
            {!loading && refills.length > 0 && (
              <div className="pd-refill-list">
                {refills.map((r) => (
                  <article key={r.id} className="pd-refill-card">
                    <div className="pd-refill-card-main">
                      <span className="material-symbols-outlined pd-refill-card-icon">medication</span>
                      <div>
                        <p className="pd-refill-card-med">
                          {r.medication_name} {r.medication_dosage || ""}
                        </p>
                        <p className="pd-muted">Reviewing doctor: {r.doctor_name}</p>
                      </div>
                    </div>
                    <div className="pd-refill-card-meta">
                      <span className={statusClass(r.status)}>{r.status}</span>
                      <span className="pd-muted pd-refill-card-date">
                        {r.requested_at ? new Date(r.requested_at).toLocaleString() : "—"}
                      </span>
                    </div>
                    {r.status === "denied" && r.denial_reason && (
                      <p className="pd-refill-denial">{r.denial_reason}</p>
                    )}
                  </article>
                ))}
              </div>
            )}
          </div>

          <div className="pd-notifications-panel">
            <h4 className="pd-notifications-panel-title">All notifications</h4>
            {loading && <p className="pd-muted">Loading notifications...</p>}
            {!loading && notifications.length === 0 && (
              <p className="pd-muted">No notifications yet.</p>
            )}
            {!loading && notifications.length > 0 && (
              <ul className="pd-notification-list">
                {notifications.map((n) => (
                  <li
                    key={n.id}
                    className={`pd-notification-card pd-notification-card--${n.type.replace(/_/g, "-")}`}
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
      </section>
    </div>
  );
}
