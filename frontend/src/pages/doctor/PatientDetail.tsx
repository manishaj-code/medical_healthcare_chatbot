import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import DoctorAppointmentsSections from "../../components/doctor/DoctorAppointmentsSections";
import DoctorPatientVisitRecords, {
  type VisitRecordsPayload,
} from "../../components/doctor/DoctorPatientVisitRecords";
import DoctorChatHistory from "../../components/doctor/DoctorChatHistory";
import DoctorPatientConsultSummary, {
  type ConsultationSummaryData,
} from "../../components/doctor/DoctorPatientConsultSummary";
import ClinicalSummaryPanel from "../../components/doctor/ClinicalSummaryPanel";
import {
  ageFromDob,
  formatDisplayDate,
  formatDoctorTime,
  isUpcomingAppointment,
  patientCaseId,
  patientInitials,
  todayIso,
} from "../../utils/doctorPortal";
import type { HealthVital } from "../../utils/healthVitals";

type PatientTab = "summary" | "chats" | "appointments";

interface PatientDetailData {
  patient_id: string;
  name: string;
  email: string;
  dob: string | null;
  gender: string | null;
  blood_group: string | null;
  appointments: { appointment_id: string; date: string; time: string; status: string }[];
  summary: string;
}

interface ChatMessage {
  role: string;
  content: string;
  created_at?: string;
}

interface PatientConversation {
  conversation_id: string;
  title: string;
  created_at: string;
  emergency_flag: boolean;
  messages: ChatMessage[];
}

interface ReportRow {
  id: string;
  analysis: Record<string, unknown> | null;
}

function parseTab(value: string | null): PatientTab {
  if (value === "chats" || value === "appointments") return value;
  return "summary";
}

export default function PatientDetail() {
  const { patientId } = useParams<{ patientId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = parseTab(searchParams.get("tab"));
  const [detail, setDetail] = useState<PatientDetailData | null>(null);
  const [conversations, setConversations] = useState<PatientConversation[]>([]);
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [healthVitals, setHealthVitals] = useState<HealthVital[]>([]);
  const [consultSummary, setConsultSummary] = useState<ConsultationSummaryData | null>(null);
  const [visitRecords, setVisitRecords] = useState<VisitRecordsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const viewRef = useRef<HTMLDivElement>(null);

  const setTab = (next: PatientTab, scroll = true) => {
    setSearchParams(next === "summary" ? {} : { tab: next }, { replace: true });
    if (scroll) {
      requestAnimationFrame(() => {
        viewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  };

  useEffect(() => {
    if (!patientId) return;
    setLoading(true);
    Promise.all([
      api<PatientDetailData>(`/api/v1/doctor/patients/${patientId}`),
      api<PatientConversation[]>(`/api/v1/doctor/patients/${patientId}/conversations`),
      api<ReportRow[]>(`/api/v1/doctor/patients/${patientId}/reports`).catch(() => []),
      api<ConsultationSummaryData>(`/api/v1/doctor/patients/${patientId}/consultation-summary`).catch(() => null),
      api<VisitRecordsPayload>(`/api/v1/doctor/patients/${patientId}/visit-records`).catch(() => null),
      api<{ vitals: HealthVital[] }>(`/api/v1/doctor/patients/${patientId}/health-vitals`).catch(() => ({
        vitals: [],
      })),
    ])
      .then(([d, chats, reps, consult, visits, vitalsRes]) => {
        setDetail(d);
        setConversations(chats);
        setReports(reps);
        setConsultSummary(consult);
        setVisitRecords(visits);
        setHealthVitals(vitalsRes.vitals ?? []);
      })
      .catch((err) => {
        console.error(err);
        setDetail(null);
      })
      .finally(() => setLoading(false));
  }, [patientId]);

  const reloadVisitRecords = async () => {
    if (!patientId) return;
    const visits = await api<VisitRecordsPayload>(`/api/v1/doctor/patients/${patientId}/visit-records`);
    setVisitRecords(visits);
    const d = await api<PatientDetailData>(`/api/v1/doctor/patients/${patientId}`);
    setDetail(d);
  };

  const markAppointmentCompleted = async (appointmentId: string) => {
    await api(`/api/v1/doctor/appointments/${appointmentId}/complete`, { method: "POST" });
    await reloadVisitRecords();
  };

  const markAppointmentCancelled = async (appointmentId: string) => {
    await api(`/api/v1/doctor/appointments/${appointmentId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason: "Cancelled by doctor — patient did not attend or visit closed." }),
    });
    await reloadVisitRecords();
  };

  useEffect(() => {
    if (tab !== "summary" && !loading) {
      viewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [tab, loading]);

  if (loading) {
    return (
      <div className="dp-loading">
        <div className="dp-spinner" />
        Loading patient record…
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="dp-empty">
        <p>Patient not found or access denied.</p>
        <button type="button" className="dp-btn dp-btn--outline" onClick={() => navigate("/doctor")}>
          Back to dashboard
        </button>
      </div>
    );
  }

  const age = ageFromDob(detail.dob);
  const upcoming = detail.appointments
    .filter((a) => isUpcomingAppointment(a.date, a.time, a.status))
    .sort((a, b) => `${a.date}${a.time}`.localeCompare(`${b.date}${b.time}`))[0];

  const hasEmergency = consultSummary?.emergency_flag || conversations.some((c) => c.emergency_flag);
  const topCondition =
    consultSummary?.conditions[0] ||
    consultSummary?.detected_symptoms[0] ||
    conversations.find((c) => c.emergency_flag)?.title;
  const conditionHint =
    topCondition || (detail.blood_group ? `Blood group ${detail.blood_group}` : "Under your care");
  const latestConversation = conversations[0];

  const tabs: { id: PatientTab; label: string; icon: string }[] = [
    { id: "summary", label: "Overview", icon: "info" },
    { id: "chats", label: `Chat history (${conversations.length})`, icon: "forum" },
    { id: "appointments", label: "Consultations", icon: "medical_services" },
  ];

  return (
    <>
      <nav className="dp-breadcrumb">
        <Link to="/doctor">Dashboard</Link>
        <span className="material-symbols-outlined">chevron_right</span>
        <strong>{detail.name}</strong>
      </nav>

      <section className="dp-patient-header">
        <div className="dp-patient-identity">
          <div className="dp-patient-photo">
            {patientInitials(detail.name)}
            <div className="dp-patient-photo-badge">
              <span className="material-symbols-outlined filled-icon">check_circle</span>
            </div>
          </div>
          <div>
            <h1 className="dp-patient-name">
              {detail.name}
              <span className="dp-id-pill">ID: {patientCaseId(detail.patient_id)}</span>
            </h1>
            <div className="dp-patient-meta">
              {age != null && (
                <span>
                  <span className="material-symbols-outlined">cake</span>
                  {age} years
                </span>
              )}
              {detail.gender && (
                <span>
                  <span className="material-symbols-outlined">person</span>
                  {detail.gender}
                </span>
              )}
              <span>
                <span className="material-symbols-outlined">emergency</span>
                {conditionHint}
              </span>
              {upcoming && (
                <span className="dp-next-appt">
                  <span className="material-symbols-outlined">calendar_today</span>
                  Next: {formatDisplayDate(upcoming.date)} at {formatDoctorTime(upcoming.time)}
                </span>
              )}
            </div>
            <p className="dp-muted-note" style={{ marginTop: 8 }}>
              {detail.email}
            </p>
          </div>
        </div>
        <div className="dp-btn-group">
          <button type="button" className="dp-btn dp-btn--ghost" onClick={() => navigate("/doctor")}>
            <span className="material-symbols-outlined">arrow_back</span>
            Dashboard
          </button>
          <button type="button" className="dp-btn dp-btn--primary" onClick={() => setTab("chats")}>
            <span className="material-symbols-outlined">forum</span>
            Chat history
          </button>
        </div>
      </section>

      <nav className="dp-tabs dp-patient-tabs" aria-label="Patient record sections">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`dp-tab${tab === t.id ? " dp-tab--active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            <span className="material-symbols-outlined">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </nav>

      <div ref={viewRef} className="dp-patient-view" id="patient-view">
        {tab === "summary" && (
          <div className="dp-detail-grid">
            <div>
              {consultSummary ? (
                <DoctorPatientConsultSummary
                  aiSummary={detail.summary}
                  consult={consultSummary}
                  latestMessages={latestConversation?.messages ?? []}
                  onOpenChats={() => setTab("chats")}
                />
              ) : (
                <div className="dp-glass dp-glass--clinical-summary">
                  <ClinicalSummaryPanel
                    summaryText={detail.summary}
                    consult={consultSummary}
                    variant="full"
                  />
                </div>
              )}

              {healthVitals.length > 0 && (
                <div className="dp-glass">
                  <div className="dp-panel-head">
                    <h2 className="dp-panel-title">Vitals History</h2>
                    <span className="dp-link dp-link--muted">From latest reports</span>
                  </div>
                  <div className="dp-vitals-grid">
                    {healthVitals.map((vital) => (
                      <div key={vital.key} className="dp-vital-card">
                        <p className="dp-vital-label">{vital.label}</p>
                        <p className="dp-vital-value">
                          {vital.value_secondary ? (
                            <>
                              {vital.value}/{vital.value_secondary}
                            </>
                          ) : (
                            vital.display
                          )}{" "}
                          <span className="dp-vital-unit">{vital.unit}</span>
                        </p>
                        {vital.source_filename && (
                          <p className="dp-vital-source">{vital.source_filename}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {reports.length > 0 && (
                <div className="dp-glass">
                  <h2 className="dp-panel-title dp-panel-title--spaced">Recent Lab Results</h2>
                  <div className="dp-table-wrap">
                    <table className="dp-table">
                      <thead>
                        <tr>
                          <th>Report</th>
                          <th>Details</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reports.map((r) => (
                          <tr key={r.id}>
                            <td className="dp-cell-bold">Report {r.id.slice(0, 8)}</td>
                            <td className="dp-cell-muted">
                              {r.analysis ? JSON.stringify(r.analysis).slice(0, 120) : "—"}…
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>

            <div>
              <div className="dp-glass">
                <h2 className="dp-panel-title dp-panel-title--spaced">Patient Info</h2>
                <ul className="dp-info-list">
                  <li>
                    <strong>Email</strong>
                    <span>{detail.email}</span>
                  </li>
                  {detail.dob && (
                    <li>
                      <strong>Date of birth</strong>
                      <span>{formatDisplayDate(detail.dob)}</span>
                    </li>
                  )}
              {detail.gender && (
                <li>
                  <strong>Gender</strong>
                  <span>{detail.gender}</span>
                </li>
              )}
              {hasEmergency && (
                <li>
                  <strong>Alert</strong>
                  <span className="dp-tag dp-tag--critical">Emergency in chat</span>
                </li>
              )}
                  {detail.blood_group && (
                    <li>
                      <strong>Blood group</strong>
                      <span>{detail.blood_group}</span>
                    </li>
                  )}
                </ul>
              </div>

              <div className="dp-glass">
                <h2 className="dp-panel-title dp-panel-title--spaced">Quick Actions</h2>
                <button type="button" className="dp-btn dp-btn--primary dp-btn--block dp-btn--spaced" onClick={() => setTab("chats")}>
                  <span className="material-symbols-outlined">forum</span>
                  View chat history
                </button>
                <button
                  type="button"
                  className="dp-btn dp-btn--outline dp-btn--block"
                  onClick={() => navigate("/doctor", { state: { tab: "refills" } })}
                >
                  Refill requests
                </button>
              </div>
            </div>
          </div>
        )}

        {tab === "chats" && (
          <div className="dp-detail-grid">
            <div className="dp-glass dp-chat-view">
              <div className="dp-panel-head">
                <div>
                  <h2 className="dp-panel-title">Chat history</h2>
                  <p className="dp-panel-desc" style={{ margin: "4px 0 0" }}>
                    Transcripts between {detail.name} and the AI health assistant.
                  </p>
                </div>
                <span className="dp-date-pill">
                  {conversations.length} session{conversations.length !== 1 ? "s" : ""}
                </span>
              </div>

              <DoctorChatHistory
                conversations={conversations}
                patientName={detail.name}
                onBack={() => setTab("summary")}
              />
            </div>

            <div>
              <div className="dp-glass">
                <h2 className="dp-panel-title dp-panel-title--spaced">Patient Info</h2>
                <ul className="dp-info-list">
                  <li>
                    <strong>Email</strong>
                    <span>{detail.email}</span>
                  </li>
                  {detail.gender && (
                    <li>
                      <strong>Gender</strong>
                      <span>{detail.gender}</span>
                    </li>
                  )}
                </ul>
              </div>
              <div className="dp-glass">
                <h2 className="dp-panel-title dp-panel-title--spaced">Quick Actions</h2>
                <button type="button" className="dp-btn dp-btn--ghost dp-btn--block dp-btn--spaced" onClick={() => setTab("summary")}>
                  <span className="material-symbols-outlined">info</span>
                  Back to overview
                </button>
                <button
                  type="button"
                  className="dp-btn dp-btn--outline dp-btn--block"
                  onClick={() => navigate("/doctor", { state: { tab: "refills" } })}
                >
                  Refill requests
                </button>
              </div>
            </div>
          </div>
        )}

        {tab === "appointments" && (
          <section className="dp-panel dp-visit-panel">
            <div className="dp-visit-panel-head">
              <div className="dp-visit-panel-intro">
                <span className="dp-visit-panel-icon material-symbols-outlined">medical_services</span>
                <div>
                  <h2 className="dp-panel-title">Consultation records</h2>
                  <p className="dp-panel-desc">
                    Visit timeline, triage summaries, clinical notes, and patient context for {detail.name}.
                  </p>
                </div>
              </div>
            </div>
            {visitRecords ? (
              <DoctorPatientVisitRecords
                data={visitRecords}
                onMarkCompleted={markAppointmentCompleted}
                onMarkCancelled={markAppointmentCancelled}
              />
            ) : (
              <DoctorAppointmentsSections appointments={detail.appointments} showPatient={false} />
            )}
          </section>
        )}
      </div>
    </>
  );
}
