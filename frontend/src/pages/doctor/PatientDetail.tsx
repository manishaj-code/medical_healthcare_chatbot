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
import DoctorPatientLabSection from "../../components/doctor/DoctorPatientLabSection";
import ClinicalSummaryPanel from "../../components/doctor/ClinicalSummaryPanel";
import DoctorPatientVideoTranscripts, {
  type VideoTranscriptRow,
} from "../../components/doctor/DoctorPatientVideoTranscripts";
import {
  ageFromDob,
  canStartConsultation,
  consultationModeLabel,
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
  appointments: {
    appointment_id: string;
    apt_id?: string;
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
  }[];
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
  created_at?: string | null;
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
  const [videoTranscripts, setVideoTranscripts] = useState<VideoTranscriptRow[]>([]);
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
      api<{ items: VideoTranscriptRow[] }>(
        `/api/v1/doctor/patients/${patientId}/video-transcripts`,
      ).catch(() => ({ items: [] })),
      api<{ vitals: HealthVital[] }>(`/api/v1/doctor/patients/${patientId}/health-vitals`).catch(() => ({
        vitals: [],
      })),
    ])
      .then(([d, chats, reps, consult, visits, videoTx, vitalsRes]) => {
        setDetail(d);
        setConversations(chats);
        setReports(reps);
        setConsultSummary(consult);
        setVisitRecords(visits);
        setVideoTranscripts(videoTx.items ?? []);
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
    const videoTx = await api<{ items: VideoTranscriptRow[] }>(
      `/api/v1/doctor/patients/${patientId}/video-transcripts`,
    ).catch(() => ({ items: [] }));
    setVideoTranscripts(videoTx.items ?? []);
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

  const conductableVisit = (() => {
    const pool =
      visitRecords?.visits.filter((v) => canStartConsultation(v.date, v.status)) ??
      detail.appointments.filter((a) => canStartConsultation(a.date, a.status));
    return [...pool].sort((a, b) => {
      const aUpcoming = isUpcomingAppointment(a.date, a.time, a.status) ? 0 : 1;
      const bUpcoming = isUpcomingAppointment(b.date, b.time, b.status) ? 0 : 1;
      if (aUpcoming !== bUpcoming) return aUpcoming - bUpcoming;
      return `${a.date}${a.time}`.localeCompare(`${b.date}${b.time}`);
    })[0];
  })();

  const showConsultBanner =
    conductableVisit &&
    isUpcomingAppointment(conductableVisit.date, conductableVisit.time, conductableVisit.status);

  const hasEmergency = consultSummary?.emergency_flag || conversations.some((c) => c.emergency_flag);
  const topCondition =
    consultSummary?.conditions[0] ||
    consultSummary?.detected_symptoms[0] ||
    conversations.find((c) => c.emergency_flag)?.title;
  const conditionHint =
    topCondition || (detail.blood_group ? `Blood group ${detail.blood_group}` : "Under your care");
  const latestConversation = conversations[0];
  const reportReviewVisit = detail.appointments.find(
    (a) => a.linked_report && a.appointment_reason && canStartConsultation(a.date, a.status),
  );

  const videoTranscriptRows = videoTranscripts;

  const tabs: { id: PatientTab; label: string; icon: string }[] = [
    { id: "summary", label: "Overview", icon: "info" },
    { id: "chats", label: `Chat history (${conversations.length})`, icon: "forum" },
    { id: "appointments", label: "Visits & consultations", icon: "medical_services" },
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
          {conductableVisit && (
            <Link
              to={`/doctor/consultation/${conductableVisit.appointment_id}`}
              className="dp-btn dp-btn--primary"
            >
              <span className="material-symbols-outlined">stethoscope</span>
              Start consultation
            </Link>
          )}
          <button
            type="button"
            className={`dp-btn ${conductableVisit ? "dp-btn--outline" : "dp-btn--primary"}`}
            onClick={() => setTab("chats")}
          >
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
          <div className="dp-detail-grid dp-detail-grid--overview">
            <div className="dp-detail-grid-main">
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

              <DoctorPatientVideoTranscripts
                patientName={detail.name}
                rows={videoTranscriptRows}
                loading={loading}
              />

              {reportReviewVisit?.linked_report && (
                <div className="dp-glass dp-report-review-card">
                  <h2 className="dp-panel-title dp-panel-title--spaced">Report for upcoming visit</h2>
                  <p className="dp-muted-note">{reportReviewVisit.appointment_reason}</p>
                  <p>
                    <strong>{reportReviewVisit.linked_report.filename}</strong>
                  </p>
                  {reportReviewVisit.linked_report.summary ? (
                    <p className="dp-report-review-summary">{reportReviewVisit.linked_report.summary}</p>
                  ) : null}
                  {(reportReviewVisit.linked_report.abnormal ?? []).length > 0 && (
                    <ul className="dp-report-review-abnormal">
                      {reportReviewVisit.linked_report.abnormal.slice(0, 6).map((item) => (
                        <li key={`${item.test}-${item.value}`}>
                          {item.test}: {item.value}
                          {item.flag ? ` (${item.flag})` : ""}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              <DoctorPatientLabSection vitals={healthVitals} reports={reports} />
            </div>

            <aside className="dp-detail-grid-aside">
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

              {consultSummary && consultSummary.medications.length > 0 && (
                <div className="dp-glass">
                  <h2 className="dp-panel-title dp-panel-title--spaced">Medications</h2>
                  <ul className="dp-overview-med-list">
                    {consultSummary.medications.map((m) => (
                      <li key={m.name}>
                        <span className="material-symbols-outlined">medication</span>
                        <div>
                          <strong>{m.name}</strong>
                          <span>
                            {[m.dosage, m.frequency].filter(Boolean).join(" · ") || "Active"}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {consultSummary && consultSummary.allergies.length > 0 && (
                <div className="dp-glass">
                  <h2 className="dp-panel-title dp-panel-title--spaced">Allergies</h2>
                  <ul className="dp-consult-chip-list dp-consult-chip-list--alert">
                    {consultSummary.allergies.map((a) => (
                      <li key={a}>{a}</li>
                    ))}
                  </ul>
                </div>
              )}

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
            </aside>
          </div>
        )}

        {tab === "chats" && (
          <div className="dp-detail-grid">
            <div className="dp-glass dp-chat-view">
              <div className="dp-panel-head">
                <div>
                  <h2 className="dp-panel-title">Chat history</h2>
                  <p className="dp-panel-desc" style={{ margin: "4px 0 0" }}>
                    AI health assistant conversations with {detail.name} (not video visit transcripts).
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
            {showConsultBanner && (
              <div className="dp-consult-cta-banner">
                <div>
                  <strong>
                    {consultationModeLabel(
                      conductableVisit.consultation_mode,
                      "is_video" in conductableVisit ? conductableVisit.is_video : undefined,
                    )}{" "}
                    visit ready
                  </strong>
                  <p>
                    Open the consultation workflow to review the AI pre-visit summary, document findings,
                    and complete the visit.
                  </p>
                </div>
                <Link
                  to={`/doctor/consultation/${conductableVisit.appointment_id}`}
                  className="dp-btn dp-btn--primary"
                >
                  <span className="material-symbols-outlined">stethoscope</span>
                  Start consultation
                </Link>
              </div>
            )}
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
                onOpenRefills={() => navigate("/doctor", { state: { tab: "refills" } })}
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
