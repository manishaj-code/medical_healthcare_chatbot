import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { formatChatText } from "../../components/ChatBookingUI";
import AppointmentCard, { AppointmentItem } from "../../components/AppointmentCard";
import { CHAT_LIST_TITLE, fetchConversations, formatChatDateLabel } from "../../utils/chatConversations";
import { buildHealthInsightsPanel } from "../../utils/healthInsights";
import { HealthVital } from "../../utils/healthVitals";

interface Conversation {
  id: string;
  title: string | null;
  created_at: string;
}

interface Report {
  id: string;
  created_at: string;
}

interface MedHistory {
  condition: string;
}

interface Medication {
  name: string;
  dosage?: string | null;
}

interface Allergy {
  allergen: string;
}

interface ActivityRow {
  id: string;
  title: string;
  subtitle: string;
  source: string;
  date: string;
  status: string;
  statusClass: string;
  action: "chat" | "view" | "download";
  link?: string;
}

function firstName(full: string): string {
  return full.trim().split(/\s+/)[0] || "there";
}

export default function PatientDashboard() {
  const [appts, setAppts] = useState<AppointmentItem[]>([]);
  const [chats, setChats] = useState<Conversation[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [history, setHistory] = useState<MedHistory[]>([]);
  const [meds, setMeds] = useState<Medication[]>([]);
  const [allergies, setAllergies] = useState<Allergy[]>([]);
  const [healthVitals, setHealthVitals] = useState<HealthVital[]>([]);
  const [loading, setLoading] = useState(true);

  const userName = localStorage.getItem("user_name") || "Patient";

  useEffect(() => {
    Promise.all([
      api<AppointmentItem[]>("/api/v1/appointments").catch(() => []),
      fetchConversations().catch(() => []),
      api<Report[]>("/api/v1/reports").catch(() => []),
      api<MedHistory[]>("/api/v1/patients/me/medical-history").catch(() => []),
      api<Medication[]>("/api/v1/patients/me/medications").catch(() => []),
      api<Allergy[]>("/api/v1/patients/me/allergies").catch(() => []),
      api<{ vitals: HealthVital[] }>("/api/v1/reports/health-vitals").catch(() => ({ vitals: [] })),
    ])
      .then(([a, c, r, h, m, al, vitalsRes]) => {
        setAppts(a);
        setChats(c);
        setReports(r);
        setHistory(h);
        setMeds(m);
        setAllergies(al);
        setHealthVitals(vitalsRes.vitals ?? []);
      })
      .finally(() => setLoading(false));
  }, []);

  const upcoming = useMemo(
    () => appts.filter((a) => a.status === "confirmed").slice(0, 3),
    [appts]
  );

  const activity = useMemo(() => {
    const rows: ActivityRow[] = [];
    for (const r of reports.slice(0, 2)) {
      rows.push({
        id: `report-${r.id}`,
        title: "Medical Report Uploaded",
        subtitle: "Lab / document analysis",
        source: "MediAI Labs",
        date: formatChatDateLabel(r.created_at),
        status: "Reviewed",
        statusClass: "status-reviewed",
        action: "download",
      });
    }
    for (const m of meds.slice(0, 1)) {
      rows.push({
        id: `med-${m.name}`,
        title: "Active Prescription",
        subtitle: `${m.name}${m.dosage ? ` ${m.dosage}` : ""}`,
        source: "Your pharmacy",
        date: "Current",
        status: "Active",
        statusClass: "status-pending",
        action: "view",
      });
    }
    for (const c of chats.slice(0, 2)) {
      rows.push({
        id: `chat-${c.id}`,
        title: c.title || CHAT_LIST_TITLE,
        subtitle: "AI health consultation",
        source: "MediAI Assistant",
        date: formatChatDateLabel(c.created_at),
        status: "Completed",
        statusClass: "status-completed",
        action: "chat",
        link: "/chat",
      });
    }
    return rows.slice(0, 5);
  }, [reports, meds, chats]);

  const healthInsights = useMemo(
    () =>
      buildHealthInsightsPanel({
        history,
        meds,
        reports,
        allergies,
        upcoming,
        chatCount: chats.length,
      }),
    [history, meds, reports, allergies, upcoming, chats.length]
  );

  const dashboardWelcome = useMemo(() => {
    const name = firstName(userName);
    const greeting = `Welcome back, ${name}.`;

    if (loading) {
      return { greeting, message: "" };
    }

    const visitCount = upcoming.length;
    const hasActivity = chats.length > 0 || reports.length > 0 || appts.length > 0;

    let message: string;
    if (visitCount > 0) {
      const next = upcoming[0];
      const when = formatChatDateLabel(`${next.date}T12:00:00`);
      const doctor = next.doctor_name || "your doctor";
      message =
        visitCount === 1
          ? `You have **1 upcoming visit** with **${doctor}** on ${when}. Review details below or chat with your AI assistant before the appointment.`
          : `You have **${visitCount} upcoming visits**. Your next is with **${doctor}** on ${when}. Stay prepared with AI Consultation and your activity summary below.`;
    } else if (hasActivity) {
      message =
        "Your health dashboard is up to date. Continue in **AI Consultation** for symptom checks, report analysis, or to book a doctor when you need one.";
    } else {
      message =
        "Your personal health hub is ready. Start **AI Consultation** to describe symptoms, upload lab reports, or find and book a doctor.";
    }

    return { greeting, message };
  }, [userName, upcoming, chats.length, reports.length, appts.length, loading]);

  return (
    <div className="patient-dashboard">
      <section className="pd-welcome">
        <div className="pd-welcome-copy">
          <h2>{dashboardWelcome.greeting}</h2>
          {!loading && dashboardWelcome.message && (
            <p className="pd-welcome-sub">{formatChatText(dashboardWelcome.message)}</p>
          )}
          {!loading && (
            <div className="pd-welcome-stats">
              {upcoming.length > 0 && (
                <span className="pd-welcome-stat">
                  <span className="material-symbols-outlined">event</span>
                  {upcoming.length} upcoming visit{upcoming.length > 1 ? "s" : ""}
                </span>
              )}
              {chats.length > 0 && (
                <span className="pd-welcome-stat">
                  <span className="material-symbols-outlined">forum</span>
                  {chats.length} consultation{chats.length > 1 ? "s" : ""}
                </span>
              )}
              {reports.length > 0 && (
                <span className="pd-welcome-stat">
                  <span className="material-symbols-outlined">description</span>
                  {reports.length} report{reports.length > 1 ? "s" : ""}
                </span>
              )}
            </div>
          )}
        </div>
        <Link to="/chat" className="pd-cta-btn">
          <span className="material-symbols-outlined">smart_toy</span>
          Start AI Consultation
        </Link>
      </section>

      {!loading && healthVitals.length > 0 && (
        <section className="pd-section">
          <div className="pd-section-head">
            <h3>Live Health Vitals</h3>
            <span className="pd-section-meta">From your uploaded reports</span>
          </div>
          <div className="pd-vitals-grid">
            {healthVitals.map((vital) => (
              <div key={vital.key} className="pd-vital-card">
                <div className="pd-vital-top">
                  <div className={`pd-vital-icon pd-vital-icon--${vital.icon_variant}`}>
                    <span className="material-symbols-outlined">{vital.icon}</span>
                  </div>
                  <span className="pd-pill">{vital.status}</span>
                </div>
                <p className="pd-vital-label">{vital.label}</p>
                <p className="pd-vital-value">
                  {vital.value_secondary ? (
                    <>
                      {vital.value}<span>/{vital.value_secondary}</span>
                    </>
                  ) : (
                    vital.display
                  )}{" "}
                  <small>{vital.unit}</small>
                </p>
                <div className="pd-vital-bar">
                  <span
                    className={vital.bar_class || undefined}
                    style={{ width: `${vital.bar_percent}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <div className="pd-split">
        <section className="pd-section pd-appointments">
          <div className="pd-section-head">
            <h3>Upcoming Appointments</h3>
            <Link to="/appointments" className="pd-link-btn">View all</Link>
          </div>
          {loading && <p className="pd-muted">Loading appointments...</p>}
          {!loading && upcoming.length === 0 && (
            <div className="pd-empty-card">
              <p>No upcoming appointments.</p>
              <Link to="/doctors" className="pd-outline-btn">Book a doctor</Link>
            </div>
          )}
          <div className="pd-appt-list">
            {upcoming.map((a) => (
              <AppointmentCard key={a.id} appointment={a} />
            ))}
          </div>
        </section>

        <section className="pd-section pd-insights">
          <h3>AI Health Insights</h3>
          <div className={`pd-insights-panel pd-insights-panel--${healthInsights.mode}`}>
            <div className="pd-insights-head">
              <div className="pd-insights-icon">
                <span className="material-symbols-outlined">
                  {healthInsights.mode === "wellness" ? "monitoring" : "auto_awesome"}
                </span>
              </div>
              <span>{healthInsights.headline}</span>
            </div>
            <div className="pd-insight-cards">
              {healthInsights.cards.map((card) => (
                <div key={card.tag} className="pd-insight-item">
                  <p className="pd-insight-tag">{card.tag}</p>
                  <p>{formatChatText(card.text)}</p>
                </div>
              ))}
            </div>
            <Link
              to={healthInsights.ctaTo}
              state={healthInsights.ctaState}
              className="pd-insights-cta"
            >
              <span className="material-symbols-outlined">
                {healthInsights.mode === "wellness" ? "assignment" : "chat_bubble"}
              </span>
              {healthInsights.ctaLabel}
            </Link>
          </div>
        </section>
      </div>

      <section className="pd-section pd-activity">
        <h3>Recent Activity</h3>
        <div className="pd-table-wrap">
          <table className="pd-table">
            <thead>
              <tr>
                <th>Event</th>
                <th>Source</th>
                <th>Date</th>
                <th>Status</th>
                <th className="pd-table-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {activity.length === 0 && !loading && (
                <tr>
                  <td colSpan={5} className="pd-muted" style={{ padding: "1.5rem" }}>
                    No recent activity yet. Start an AI consultation to begin.
                  </td>
                </tr>
              )}
              {activity.map((row) => (
                <tr key={row.id}>
                  <td>
                    <p className="pd-table-title">{row.title}</p>
                    <p className="pd-table-sub">{row.subtitle}</p>
                  </td>
                  <td>{row.source}</td>
                  <td>{row.date}</td>
                  <td><span className={`pd-status-pill ${row.statusClass}`}>{row.status}</span></td>
                  <td className="pd-table-actions">
                    {row.link ? (
                      <Link to={row.link} className="pd-icon-action" title="Open">
                        <span className="material-symbols-outlined">chat_bubble_outline</span>
                      </Link>
                    ) : (
                      <button type="button" className="pd-icon-action" title="View">
                        <span className="material-symbols-outlined">
                          {row.action === "download" ? "download" : "visibility"}
                        </span>
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
