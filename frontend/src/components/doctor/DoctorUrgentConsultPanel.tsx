import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";

export interface UrgentConsultItem {
  offer_id: string;
  request_id: string;
  offer_status: string;
  request_status: string;
  patient_id: string;
  patient_name: string;
  patient_email?: string | null;
  patient_phone?: string | null;
  patient_dob?: string | null;
  patient_gender?: string | null;
  patient_blood_group?: string | null;
  symptoms: string[];
  specialty: string;
  risk_level: string;
  patient_message?: string;
  created_at?: string;
  notified_at?: string;
  responded_at?: string;
  expires_at?: string;
  assigned_at?: string;
  accepted_doctor_name?: string | null;
  appointment_id?: string | null;
  apt_id?: string | null;
  history_bucket?: string;
  can_accept: boolean;
}

type UrgentTab = "pending" | "attended" | "declined" | "missed";

const TAB_META: Record<
  UrgentTab,
  { label: string; emptyIcon: string; emptyTitle: string; emptyDesc: string }
> = {
  pending: {
    label: "Pending",
    emptyIcon: "check_circle",
    emptyTitle: "No patients waiting",
    emptyDesc: "New urgent consult requests will appear here with accept and decline actions.",
  },
  attended: {
    label: "Attended",
    emptyIcon: "videocam",
    emptyTitle: "No attended cases yet",
    emptyDesc: "Patients you accept for urgent video consult will be listed here for audit.",
  },
  declined: {
    label: "Declined",
    emptyIcon: "block",
    emptyTitle: "No declined cases",
    emptyDesc: "Requests you decline are saved here with full patient details.",
  },
  missed: {
    label: "Attended by another doctor",
    emptyIcon: "person_off",
    emptyTitle: "No cases attended by others",
    emptyDesc: "When another doctor accepts the urgent consult before you, it is listed here for audit.",
  },
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

function formatWhen(iso?: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function timeAgo(iso?: string | null): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function expiresIn(iso?: string | null): string | null {
  if (!iso) return null;
  const diff = new Date(iso).getTime() - Date.now();
  if (diff <= 0) return "Expired";
  const mins = Math.ceil(diff / 60000);
  if (mins < 60) return `Expires in ${mins}m`;
  return `Expires in ${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function riskLabel(level: string): string {
  if (level === "emergency") return "Emergency";
  if (level === "high") return "High risk";
  return level.charAt(0).toUpperCase() + level.slice(1);
}

function statusLabel(item: UrgentConsultItem, tab: UrgentTab): string {
  if (tab === "attended" || item.offer_status === "accepted") return "Attended";
  if (tab === "declined" || item.offer_status === "declined") return "Declined";
  if (tab === "missed" || item.offer_status === "superseded") {
    return item.accepted_doctor_name
      ? `Attended by ${item.accepted_doctor_name}`
      : "Attended by another doctor";
  }
  return "Awaiting response";
}

function UrgentEmpty({ tab }: { tab: UrgentTab }) {
  const meta = TAB_META[tab];
  return (
    <div className="dp-empty dp-urgent-empty-state">
      <div className="dp-empty-icon">
        <span className="material-symbols-outlined">{meta.emptyIcon}</span>
      </div>
      <p className="dp-empty-title">{meta.emptyTitle}</p>
      <p>{meta.emptyDesc}</p>
    </div>
  );
}

function PatientDetailsPanel({ item, defaultOpen }: { item: UrgentConsultItem; defaultOpen: boolean }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(defaultOpen);
  const rows = [
    { icon: "mail", label: "Email", value: item.patient_email },
    { icon: "call", label: "Phone", value: item.patient_phone },
    { icon: "cake", label: "DOB", value: item.patient_dob },
    { icon: "person", label: "Gender", value: item.patient_gender },
    { icon: "bloodtype", label: "Blood", value: item.patient_blood_group },
  ].filter((row) => row.value);

  return (
    <div className="dp-urgent-patient-panel">
      <button
        type="button"
        className="dp-urgent-patient-toggle"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="material-symbols-outlined">contact_page</span>
        Patient details
        <span className={`material-symbols-outlined dp-urgent-chevron${open ? " dp-urgent-chevron--open" : ""}`}>
          expand_more
        </span>
      </button>
      {open && (
        <div className="dp-urgent-patient-body">
          {rows.length > 0 ? (
            <ul className="dp-urgent-contact-list">
              {rows.map((row) => (
                <li key={row.label}>
                  <span className="material-symbols-outlined">{row.icon}</span>
                  <div>
                    <span className="dp-urgent-contact-label">{row.label}</span>
                    <span className="dp-urgent-contact-value">{row.value}</span>
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="dp-muted">Limited profile on file — open full profile for more.</p>
          )}
          <button
            type="button"
            className="dp-btn dp-btn--outline dp-btn--sm"
            onClick={() => navigate(`/doctor/patients/${item.patient_id}`)}
          >
            <span className="material-symbols-outlined">open_in_new</span>
            View full profile
          </button>
        </div>
      )}
    </div>
  );
}

function PendingUrgentCard({
  item,
  actingId,
  onAccept,
  onDecline,
}: {
  item: UrgentConsultItem;
  actingId: string | null;
  onAccept: (requestId: string) => void;
  onDecline: (requestId: string) => void;
}) {
  const expiry = expiresIn(item.expires_at);
  const busy = actingId === item.request_id;

  return (
    <article className={`dp-urgent-card dp-urgent-card--pending dp-urgent-card--${item.risk_level}`}>
      <div className="dp-urgent-card-live" aria-hidden>
        <span className="dp-urgent-pulse" />
        Live request
      </div>

      <div className="dp-urgent-card-layout">
        <div className="dp-urgent-card-main">
          <div className="dp-urgent-card-top">
            <div className="dp-urgent-avatar" aria-hidden>
              {initials(item.patient_name)}
            </div>
            <div className="dp-urgent-card-intro">
              <div className="dp-urgent-card-title-row">
                <h4>{item.patient_name}</h4>
                <span className={`dp-urgent-badge dp-urgent-badge--${item.risk_level}`}>
                  {riskLabel(item.risk_level)}
                </span>
              </div>
              <div className="dp-urgent-meta-row">
                <span className="dp-urgent-chip">
                  <span className="material-symbols-outlined">medical_services</span>
                  {item.specialty}
                </span>
                <span className="dp-urgent-chip">
                  <span className="material-symbols-outlined">schedule</span>
                  {timeAgo(item.created_at)}
                </span>
                {expiry && (
                  <span className={`dp-urgent-chip dp-urgent-chip--warn${expiry === "Expired" ? " dp-urgent-chip--danger" : ""}`}>
                    <span className="material-symbols-outlined">timer</span>
                    {expiry}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="dp-urgent-symptom-block">
            <p className="dp-urgent-symptom-label">Reported symptoms</p>
            <div className="dp-urgent-symptom-tags">
              {(item.symptoms?.length ? item.symptoms : ["Urgent symptoms"]).map((s) => (
                <span key={s} className="dp-urgent-symptom-tag">
                  {s}
                </span>
              ))}
            </div>
            {item.patient_message && (
              <blockquote className="dp-urgent-quote">"{item.patient_message}"</blockquote>
            )}
          </div>

          <PatientDetailsPanel item={item} defaultOpen />
        </div>

        <div className="dp-urgent-card-aside">
          <p className="dp-urgent-aside-hint">First to accept starts the video consult.</p>
          <button
            type="button"
            className="dp-btn dp-btn--primary dp-urgent-accept-btn"
            disabled={busy || !item.can_accept}
            onClick={() => onAccept(item.request_id)}
          >
            <span className="material-symbols-outlined">videocam</span>
            {busy ? "Connecting…" : "Accept & join video"}
          </button>
          <button
            type="button"
            className="dp-btn dp-btn--outline dp-urgent-decline-btn"
            disabled={busy}
            onClick={() => onDecline(item.request_id)}
          >
            Decline
          </button>
        </div>
      </div>
    </article>
  );
}

function UrgentHistoryTable({
  items,
  tab,
}: {
  items: UrgentConsultItem[];
  tab: Exclude<UrgentTab, "pending">;
}) {
  const navigate = useNavigate();

  return (
    <div className="dp-table-wrap dp-urgent-table-wrap">
      <table className="dp-table dp-urgent-table">
        <thead>
          <tr>
            <th>Patient</th>
            <th>Symptoms</th>
            <th>Risk</th>
            <th>When</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.offer_id}>
              <td>
                <div className="dp-table-patient">
                  <span className="dp-urgent-avatar dp-urgent-avatar--sm">{initials(item.patient_name)}</span>
                  <div>
                    <strong>{item.patient_name}</strong>
                    {item.patient_email && <span className="dp-urgent-table-sub">{item.patient_email}</span>}
                    {item.patient_phone && <span className="dp-urgent-table-sub">{item.patient_phone}</span>}
                  </div>
                </div>
              </td>
              <td>
                <span className="dp-urgent-table-symptoms">
                  {(item.symptoms || []).join(", ") || "—"}
                </span>
                {item.apt_id && <span className="dp-urgent-table-sub">Appt {item.apt_id}</span>}
              </td>
              <td>
                <span className={`dp-urgent-badge dp-urgent-badge--${item.risk_level}`}>
                  {riskLabel(item.risk_level)}
                </span>
              </td>
              <td>
                <span>{formatWhen(item.responded_at || item.created_at)}</span>
                <span className="dp-urgent-table-sub">{timeAgo(item.responded_at || item.created_at)}</span>
              </td>
              <td>
                <span className={`dp-urgent-status dp-urgent-status--${tab}`}>{statusLabel(item, tab)}</span>
              </td>
              <td>
                <button
                  type="button"
                  className="dp-btn dp-btn--outline dp-btn--sm"
                  onClick={() => navigate(`/doctor/patients/${item.patient_id}`)}
                >
                  Profile
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DoctorUrgentConsultPanel() {
  const [tab, setTab] = useState<UrgentTab>("pending");
  const [pending, setPending] = useState<UrgentConsultItem[]>([]);
  const [history, setHistory] = useState<Record<Exclude<UrgentTab, "pending">, UrgentConsultItem[]>>({
    attended: [],
    declined: [],
    missed: [],
  });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actingId, setActingId] = useState<string | null>(null);

  const loadPending = useCallback(async () => {
    const rows = await api<UrgentConsultItem[]>("/api/v1/doctor/urgent-consult/pending");
    return rows.filter(
      (item, index, all) => all.findIndex((row) => row.request_id === item.request_id) === index
    );
  }, []);

  const loadHistory = useCallback(async () => {
    const [attended, declined, missed] = await Promise.all([
      api<UrgentConsultItem[]>("/api/v1/doctor/urgent-consult/history?bucket=attended"),
      api<UrgentConsultItem[]>("/api/v1/doctor/urgent-consult/history?bucket=declined"),
      api<UrgentConsultItem[]>("/api/v1/doctor/urgent-consult/history?bucket=missed"),
    ]);
    return { attended, declined, missed };
  }, []);

  const loadAll = useCallback(
    async (silent = false) => {
      if (!silent) setRefreshing(true);
      try {
        const [pendingResult, historyResult] = await Promise.allSettled([loadPending(), loadHistory()]);
        if (pendingResult.status === "fulfilled") {
          setPending(pendingResult.value);
        } else {
          console.error(pendingResult.reason);
        }
        if (historyResult.status === "fulfilled") {
          setHistory(historyResult.value);
        } else {
          console.error(historyResult.reason);
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [loadPending, loadHistory]
  );

  useEffect(() => {
    void loadAll();
    const timer = window.setInterval(() => {
      void loadPending().then(setPending).catch(console.error);
    }, 5000);
    return () => window.clearInterval(timer);
  }, [loadAll, loadPending]);

  useEffect(() => {
    if (tab === "pending") return;
    void loadHistory()
      .then(setHistory)
      .catch(console.error);
  }, [tab, loadHistory]);

  const accept = async (requestId: string) => {
    setActingId(requestId);
    try {
      const res = await api<{ doctor_join_url?: string; join_url?: string }>(
        `/api/v1/doctor/urgent-consult/${requestId}/accept`,
        { method: "POST" }
      );
      await loadAll(true);
      const url = res.doctor_join_url || res.join_url;
      if (url) window.open(url, "_blank", "noopener,noreferrer");
      setTab("attended");
    } catch (err) {
      console.error(err);
      await loadAll(true);
    }
    setActingId(null);
  };

  const decline = async (requestId: string) => {
    setActingId(requestId);
    try {
      await api(`/api/v1/doctor/urgent-consult/${requestId}/decline`, { method: "POST" });
      await loadAll(true);
      setTab("declined");
    } catch (err) {
      console.error(err);
    }
    setActingId(null);
  };

  if (loading) {
    return (
      <section className="dp-panel dp-urgent-panel dp-urgent-panel--loading">
        <div className="dp-urgent-skeleton" />
      </section>
    );
  }

  const tabs: { id: UrgentTab; count: number }[] = [
    { id: "pending", count: pending.length },
    { id: "attended", count: history.attended.length },
    { id: "declined", count: history.declined.length },
    { id: "missed", count: history.missed.length },
  ];

  const activeItems =
    tab === "pending"
      ? pending
      : tab === "attended"
        ? history.attended
        : tab === "declined"
          ? history.declined
          : history.missed;

  return (
    <section className="dp-panel dp-urgent-panel">
      <div className="dp-panel-head">
        <div className="dp-urgent-head-text">
          <h2 className="dp-panel-title">
            <span className="material-symbols-outlined dp-urgent-title-icon">emergency</span>
            Urgent consults
          </h2>
          <p className="dp-panel-desc">
            Respond to live requests or review attended and declined cases for audit.
          </p>
        </div>
        <button
          type="button"
          className="dp-btn dp-btn--outline dp-btn--sm"
          disabled={refreshing}
          onClick={() => void loadAll()}
        >
          <span className={`material-symbols-outlined${refreshing ? " dp-spin" : ""}`}>refresh</span>
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div className="dp-urgent-stats">
        <div className={`dp-urgent-stat${pending.length ? " dp-urgent-stat--alert" : ""}`}>
          <span className="dp-urgent-stat-value">{pending.length}</span>
          <span className="dp-urgent-stat-label">Waiting now</span>
        </div>
        <div className="dp-urgent-stat">
          <span className="dp-urgent-stat-value">{history.attended.length}</span>
          <span className="dp-urgent-stat-label">Attended</span>
        </div>
        <div className="dp-urgent-stat">
          <span className="dp-urgent-stat-value">{history.declined.length}</span>
          <span className="dp-urgent-stat-label">Declined</span>
        </div>
        <div className="dp-urgent-stat">
          <span className="dp-urgent-stat-value">{history.missed.length}</span>
          <span className="dp-urgent-stat-label">Attended by other</span>
        </div>
      </div>

      <nav className="dp-urgent-tabs" aria-label="Urgent consult views">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`dp-urgent-tab${tab === t.id ? " dp-urgent-tab--active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {TAB_META[t.id].label}
            {t.count > 0 && (
              <span className={`dp-urgent-tab-count${t.id === "pending" && t.count > 0 ? " dp-urgent-tab-count--alert" : ""}`}>
                {t.count}
              </span>
            )}
          </button>
        ))}
      </nav>

      {activeItems.length === 0 ? (
        <UrgentEmpty tab={tab} />
      ) : tab === "pending" ? (
        <div className="dp-urgent-list">
          {pending.map((item) => (
            <PendingUrgentCard
              key={item.request_id}
              item={item}
              actingId={actingId}
              onAccept={(id) => void accept(id)}
              onDecline={(id) => void decline(id)}
            />
          ))}
        </div>
      ) : (
        <UrgentHistoryTable items={activeItems} tab={tab} />
      )}
    </section>
  );
}
