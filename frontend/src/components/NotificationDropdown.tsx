import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useNotifications } from "../hooks/useNotifications";
import { formatNotificationTime, typeIcon, typeLabel } from "../utils/notifications";

interface Props {
  apiPrefix: string;
  viewAllPath: string;
  variant?: "pill" | "icon" | "doctor";
}

export default function NotificationDropdown({
  apiPrefix,
  viewAllPath,
  variant = "pill",
}: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const { unreadCount, notifications, loading, fetchPreview, markRead } = useNotifications(apiPrefix);

  useEffect(() => {
    if (!open) return;
    void (async () => {
      await fetchPreview(5);
      await markRead();
    })();
  }, [open, fetchPreview, markRead]);

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const triggerClass =
    variant === "doctor"
      ? "dp-icon-btn notify-dropdown-trigger--doctor"
      : variant === "icon"
        ? "consult-topbar-notify"
        : "patient-topbar-notify";

  const badge =
    unreadCount > 0 ? (
      <span className="notify-dropdown-badge" aria-hidden="true">
        {unreadCount > 9 ? "9+" : unreadCount}
      </span>
    ) : null;

  return (
    <div className={`notify-dropdown${variant === "doctor" ? " notify-dropdown--doctor" : ""}`} ref={rootRef}>
      <button
        type="button"
        className={triggerClass}
        title="Notifications"
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : "Notifications"}
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="material-symbols-outlined">notifications</span>
        {variant === "pill" && (
          <span className="patient-topbar-notify-label">Notifications</span>
        )}
        {badge}
      </button>

      {open && (
        <div className="notify-dropdown-panel" role="menu">
          <div className="notify-dropdown-header">
            <h3>Notifications</h3>
          </div>

          <div className="notify-dropdown-body">
            {loading && <p className="notify-dropdown-muted">Loading notifications...</p>}
            {!loading && notifications.length === 0 && (
              <p className="notify-dropdown-muted">No notifications yet.</p>
            )}
            {!loading && notifications.length > 0 && (
              <ul className="notify-dropdown-list">
                {notifications.map((n) => (
                  <li
                    key={n.id}
                    className={`notify-dropdown-item notify-dropdown-item--${n.type.replace(/_/g, "-")}${n.is_read ? "" : " notify-dropdown-item--unread"}`}
                  >
                    <span className="material-symbols-outlined notify-dropdown-item-icon">
                      {typeIcon(n.type)}
                    </span>
                    <div className="notify-dropdown-item-content">
                      <div className="notify-dropdown-item-head">
                        <span className="notify-dropdown-item-type">{typeLabel(n.type)}</span>
                        <time className="notify-dropdown-item-time">
                          {formatNotificationTime(n.sent_at)}
                        </time>
                      </div>
                      <p className="notify-dropdown-item-message">{n.message}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="notify-dropdown-footer">
            <Link
              to={viewAllPath}
              className="notify-dropdown-view-all"
              onClick={() => setOpen(false)}
            >
              View All Notifications
              <span className="material-symbols-outlined">arrow_forward</span>
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
