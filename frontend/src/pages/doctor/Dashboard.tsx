import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate, useOutletContext } from "react-router-dom";
import { api } from "../../api/client";
import DoctorConsultationHistory, {
  type ConsultationHistoryRecord,
} from "../../components/doctor/DoctorConsultationHistory";
import DoctorAppointmentsSections from "../../components/doctor/DoctorAppointmentsSections";
import DoctorAvailabilityGrid from "../../components/doctor/DoctorAvailabilityGrid";
import DoctorUrgentConsultPanel from "../../components/doctor/DoctorUrgentConsultPanel";
import { RefillTableSkeleton } from "../../components/skeleton";
import type { DoctorOutletContext, DoctorTab } from "../../components/doctor/DoctorLayout";
import ClinicalSummaryPanel from "../../components/doctor/ClinicalSummaryPanel";
import type { ConsultationSummaryData } from "../../components/doctor/DoctorPatientConsultSummary";
import {
  DoctorAppointment,
  DoctorPatient,
  canStartConsultation,
  filterBookableSlots,
  formatDisplayDate,
  formatDoctorTime,
  isActiveAppointmentStatus,
  isAppointmentPast,
  patientCaseId,
  patientInitials,
  priorityQueueDescForDate,
  queueTagForScheduleDate,
  queueVisitMetaForDate,
  scheduleHeadingForDate,
  shiftIsoDate,
  todayIso,
} from "../../utils/doctorPortal";

interface RefillRequest {
  id: string;
  patient_id: string;
  patient_name: string;
  medication_name: string;
  medication_dosage: string | null;
  medication_frequency: string | null;
  status: string;
  denial_reason: string | null;
  requested_at: string | null;
  reviewed_at: string | null;
}

interface QueueItem {
  patientId: string;
  name: string;
  meta: string;
  tags: { label: string; variant: "critical" | "info" | "warning" }[];
  summary: string;
}

function EmptyBlock({ icon, title, desc, action }: { icon: string; title: string; desc: string; action?: ReactNode }) {
  return (
    <div className="dp-empty">
      <div className="dp-empty-icon">
        <span className="material-symbols-outlined">{icon}</span>
      </div>
      <p className="dp-empty-title">{title}</p>
      <p>{desc}</p>
      {action}
    </div>
  );
}

export default function DoctorDashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const { search, activeTab, setActiveTab } = useOutletContext<DoctorOutletContext>();
  const [consultationHistory, setConsultationHistory] = useState<ConsultationHistoryRecord[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [appointments, setAppointments] = useState<DoctorAppointment[]>([]);
  const [patients, setPatients] = useState<DoctorPatient[]>([]);
  const [mySlots, setMySlots] = useState<{ date: string; time: string }[]>([]);
  const [refillRequests, setRefillRequests] = useState<RefillRequest[]>([]);
  const [refillLoading, setRefillLoading] = useState(false);
  const [seedingSlots, setSeedingSlots] = useState(false);
  const [denyTarget, setDenyTarget] = useState<RefillRequest | null>(null);
  const [denyReason, setDenyReason] = useState("Please schedule a follow-up visit before refilling.");
  const [queueSummaries, setQueueSummaries] = useState<Record<string, string>>({});
  const [queueConsult, setQueueConsult] = useState<Record<string, ConsultationSummaryData | null>>({});
  const [scheduleDate, setScheduleDate] = useState(() => todayIso());
  const loadedSummaryIds = useRef<Set<string>>(new Set());
  const prevTabRef = useRef<DoctorTab>(activeTab);

  const resetScheduleToToday = () => setScheduleDate(todayIso());

  const activateTab = (tab: DoctorTab) => {
    if (tab === "overview") resetScheduleToToday();
    setActiveTab(tab);
  };

  const loadRefills = async () => {
    setRefillLoading(true);
    try {
      const rows = await api<RefillRequest[]>("/api/v1/doctor/refill-requests");
      setRefillRequests(rows);
    } catch (err) {
      console.error(err);
      setRefillRequests([]);
    }
    setRefillLoading(false);
  };

  const loadConsultationHistory = async (silent = false) => {
    if (!silent) setHistoryLoading(true);
    try {
      const data = await api<{ records: ConsultationHistoryRecord[]; total: number }>(
        "/api/v1/doctor/consultation-history",
      );
      setConsultationHistory(data.records ?? []);
    } catch (err) {
      console.error(err);
      if (!silent) setConsultationHistory([]);
    }
    if (!silent) setHistoryLoading(false);
  };

  const markAppointmentCompleted = async (appointmentId: string) => {
    await api(`/api/v1/doctor/appointments/${appointmentId}/complete`, { method: "POST" });
    await Promise.all([
      loadConsultationHistory(true),
      api<DoctorAppointment[]>("/api/v1/doctor/appointments").then(setAppointments),
    ]);
  };

  const markAppointmentCancelled = async (appointmentId: string) => {
    await api(`/api/v1/doctor/appointments/${appointmentId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason: "Cancelled by doctor — patient did not attend or visit closed." }),
    });
    await Promise.all([
      loadConsultationHistory(true),
      api<DoctorAppointment[]>("/api/v1/doctor/appointments").then(setAppointments),
    ]);
  };

  useEffect(() => {
    const tabFromNav = (location.state as { tab?: DoctorTab } | null)?.tab;
    if (tabFromNav) activateTab(tabFromNav);
  }, [location.state]);

  useEffect(() => {
    if (activeTab === "overview" && prevTabRef.current !== "overview") {
      resetScheduleToToday();
    }
    prevTabRef.current = activeTab;
  }, [activeTab]);

  useEffect(() => {
    api<DoctorAppointment[]>("/api/v1/doctor/appointments").then(setAppointments).catch(console.error);
    api<DoctorPatient[]>("/api/v1/doctor/patients").then(setPatients).catch(console.error);
    api<{ date: string; time: string }[]>("/api/v1/doctor/availability").then(setMySlots).catch(console.error);
    void loadRefills();
  }, []);

  useEffect(() => {
    if (activeTab === "history") void loadConsultationHistory();
  }, [activeTab]);

  const today = todayIso();
  const todayLabel = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  const doctorName = localStorage.getItem("user_name") || "Doctor";
  const greeting = (() => {
    const h = new Date().getHours();
    if (h < 12) return "Good morning";
    if (h < 17) return "Good afternoon";
    return "Good evening";
  })();

  const bookableSlots = useMemo(() => filterBookableSlots(mySlots), [mySlots]);

  const todayAppts = useMemo(
    () => appointments.filter((a) => a.date === today).sort((a, b) => a.time.localeCompare(b.time)),
    [appointments, today],
  );

  const scheduleAppts = useMemo(
    () =>
      appointments
        .filter((a) => a.date === scheduleDate && isActiveAppointmentStatus(a.status))
        .sort((a, b) => a.time.localeCompare(b.time)),
    [appointments, scheduleDate],
  );

  const scheduleHeading = scheduleHeadingForDate(scheduleDate, today);
  const scheduleIsToday = scheduleDate === today;
  const priorityQueueDesc = priorityQueueDescForDate(scheduleDate, today);

  const pendingRefills = refillRequests.filter((r) => r.status === "pending");

  const filteredPatients = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return patients;
    return patients.filter((p) => p.name.toLowerCase().includes(q));
  }, [patients, search]);

  const currentApptId = useMemo(() => {
    if (!scheduleIsToday) return null;
    const now = Date.now();
    let current: string | null = null;
    for (const a of scheduleAppts) {
      const slot = new Date(`${a.date}T${a.time}`).getTime();
      if (slot <= now + 30 * 60 * 1000 && a.status !== "completed") {
        current = a.appointment_id;
      }
    }
    if (!current) {
      const upcoming = scheduleAppts.find((a) => a.status !== "completed");
      if (upcoming) current = upcoming.appointment_id;
    }
    return current;
  }, [scheduleAppts, scheduleIsToday]);

  const urgentQueue: QueueItem[] = useMemo(() => {
    const items: QueueItem[] = [];
    const seen = new Set<string>();

    for (const r of pendingRefills.slice(0, 3)) {
      seen.add(r.patient_id);
      items.push({
        patientId: r.patient_id,
        name: r.patient_name,
        meta: `Refill request · ${r.medication_name}`,
        tags: [
          { label: "Urgent", variant: "critical" },
          { label: "Refill", variant: "warning" },
        ],
        summary: `Patient requested refill for ${r.medication_name}. Review dosage and last visit before approving.`,
      });
    }

    for (const a of scheduleAppts) {
      if (seen.has(a.patient_id) || items.length >= 4) continue;
      if (a.status === "completed") continue;
      seen.add(a.patient_id);
      const dateTag = queueTagForScheduleDate(scheduleDate, today);
      items.push({
        patientId: a.patient_id,
        name: a.patient_name,
        meta: queueVisitMetaForDate(scheduleDate, a.time, a.patient_id, today),
        tags: [
          {
            label: scheduleIsToday && a.appointment_id === currentApptId ? "Now" : dateTag,
            variant: "info",
          },
        ],
        summary: "Loading clinical summary…",
      });
    }

    return items;
  }, [pendingRefills, scheduleAppts, scheduleDate, scheduleIsToday, today, currentApptId]);

  useEffect(() => {
    const ids = urgentQueue.map((q) => q.patientId).filter((id) => !loadedSummaryIds.current.has(id));
    if (ids.length === 0) return;
    ids.forEach((id) => loadedSummaryIds.current.add(id));
    Promise.all(
      ids.map((id) =>
        Promise.all([
          api<{ summary: string }>(`/api/v1/doctor/patients/${id}`)
            .then((d) => d.summary)
            .catch(() => "No AI summary available yet."),
          api<ConsultationSummaryData>(`/api/v1/doctor/patients/${id}/consultation-summary`).catch(() => null),
        ]).then(([summary, consult]) => ({ id, summary, consult })),
      ),
    ).then((rows) => {
      setQueueSummaries((prev) => {
        const next = { ...prev };
        for (const r of rows) next[r.id] = r.summary;
        return next;
      });
      setQueueConsult((prev) => {
        const next = { ...prev };
        for (const r of rows) next[r.id] = r.consult;
        return next;
      });
    });
  }, [urgentQueue]);

  const seedSlots = async () => {
    setSeedingSlots(true);
    try {
      await api("/api/v1/doctor/availability/seed-default", { method: "POST" });
      const slots = await api<{ date: string; time: string }[]>("/api/v1/doctor/availability");
      setMySlots(slots);
    } finally {
      setSeedingSlots(false);
    }
  };

  const approveRefill = async (requestId: string) => {
    await api(`/api/v1/doctor/refill-requests/${requestId}/approve`, { method: "POST" });
    await loadRefills();
  };

  const submitDeny = async () => {
    if (!denyTarget) return;
    await api(`/api/v1/doctor/refill-requests/${denyTarget.id}/deny`, {
      method: "POST",
      body: JSON.stringify({ reason: denyReason.trim() || undefined }),
    });
    setDenyTarget(null);
    setDenyReason("Please schedule a follow-up visit before refilling.");
    await loadRefills();
  };

  const openPatient = (patientId: string) => navigate(`/doctor/patients/${patientId}`);

  const completedToday = todayAppts.filter(
    (a) => a.status === "completed" || (isAppointmentPast(a.date, a.time) && a.status !== "cancelled"),
  ).length;

  const tabs: { id: DoctorTab; label: string; icon: string; badge?: number }[] = [
    { id: "overview", label: "Overview", icon: "dashboard" },
    { id: "refills", label: "Refills", icon: "medication", badge: pendingRefills.length || undefined },
    { id: "patients", label: "Patients", icon: "group", badge: patients.length || undefined },
    { id: "appointments", label: "Appointments", icon: "event" },
    { id: "history", label: "Consultation history", icon: "history" },
    { id: "slots", label: "Availability", icon: "schedule" },
  ];

  return (
    <>
      <section className="dp-hero">
        <div>
          <h1 className="dp-hero-title">
            {greeting}, {doctorName.startsWith("Dr.") ? doctorName : `Dr. ${doctorName}`}
          </h1>
          <p className="dp-hero-sub">{todayLabel} · Your clinical workspace is ready.</p>
        </div>
        <div className="dp-hero-actions">
          <button type="button" className="dp-hero-btn" onClick={() => activateTab("overview")}>
            <span className="material-symbols-outlined">event</span>
            Today ({todayAppts.length})
          </button>
          {pendingRefills.length > 0 && (
            <button type="button" className="dp-hero-btn" onClick={() => activateTab("refills")}>
              <span className="material-symbols-outlined">medication</span>
              {pendingRefills.length} refill{pendingRefills.length !== 1 ? "s" : ""} pending
            </button>
          )}
          <button type="button" className="dp-hero-btn" onClick={() => activateTab("slots")}>
            <span className="material-symbols-outlined">add</span>
            Manage slots
          </button>
        </div>
      </section>

      <div className="dp-stats">
        <div className="dp-stat-card">
          <div>
            <p className="dp-stat-label">Today&apos;s visits</p>
            <p className="dp-stat-value dp-stat-value--primary">{todayAppts.length}</p>
            <p className="dp-stat-meta">{completedToday} completed</p>
          </div>
          <div className="dp-stat-icon dp-stat-icon--primary">
            <span className="material-symbols-outlined filled-icon">calendar_today</span>
          </div>
        </div>
        <div className="dp-stat-card">
          <div>
            <p className="dp-stat-label">Needs review</p>
            <p className="dp-stat-value dp-stat-value--danger">{pendingRefills.length}</p>
            <p className="dp-stat-meta">Pending refill requests</p>
          </div>
          <div className="dp-stat-icon dp-stat-icon--danger">
            <span className="material-symbols-outlined filled-icon">priority_high</span>
          </div>
        </div>
        <div className="dp-stat-card">
          <div>
            <p className="dp-stat-label">Your patients</p>
            <p className="dp-stat-value">{patients.length}</p>
            <p className="dp-stat-meta">{bookableSlots.length} open booking slots</p>
          </div>
          <div className="dp-stat-icon dp-stat-icon--neutral">
            <span className="material-symbols-outlined filled-icon">groups</span>
          </div>
        </div>
      </div>

      <nav className="dp-tabs" aria-label="Dashboard sections">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`dp-tab${activeTab === t.id ? " dp-tab--active" : ""}`}
            onClick={() => activateTab(t.id)}
          >
            <span className="material-symbols-outlined">{t.icon}</span>
            {t.label}
            {t.badge != null && t.badge > 0 && <span className="dp-tab-badge">{t.badge}</span>}
          </button>
        ))}
      </nav>

      {activeTab === "overview" && (
        <div className="dp-dashboard-grid" id="schedule">
          <DoctorUrgentConsultPanel />
          <section className="dp-panel">
            <div className="dp-panel-head dp-schedule-head">
              <h2 className="dp-panel-title">{scheduleHeading}</h2>
              <div className="dp-schedule-nav">
                <div className="dp-schedule-nav-group">
                  <button
                    type="button"
                    className="dp-schedule-nav-btn"
                    onClick={() => setScheduleDate((d) => shiftIsoDate(d, -1))}
                    aria-label="Previous day"
                  >
                    <span className="material-symbols-outlined">chevron_left</span>
                  </button>
                  <label className="dp-schedule-date-picker">
                    <span className="dp-schedule-date-label">
                      {new Date(`${scheduleDate}T12:00:00`).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        year: scheduleDate.slice(0, 4) !== today.slice(0, 4) ? "numeric" : undefined,
                      })}
                    </span>
                    <input
                      type="date"
                      value={scheduleDate}
                      onChange={(e) => e.target.value && setScheduleDate(e.target.value)}
                      aria-label="Pick schedule date"
                    />
                  </label>
                  <button
                    type="button"
                    className="dp-schedule-nav-btn"
                    onClick={() => setScheduleDate((d) => shiftIsoDate(d, 1))}
                    aria-label="Next day"
                  >
                    <span className="material-symbols-outlined">chevron_right</span>
                  </button>
                </div>
                {!scheduleIsToday && (
                  <button
                    type="button"
                    className="dp-schedule-today-btn"
                    onClick={() => setScheduleDate(today)}
                  >
                    <span className="material-symbols-outlined">today</span>
                    Today
                  </button>
                )}
              </div>
            </div>
            {scheduleAppts.length === 0 ? (
              <EmptyBlock
                icon="event_busy"
                title={scheduleIsToday ? "No visits today" : "No visits on this day"}
                desc={
                  scheduleIsToday
                    ? "When patients book with you, appointments will appear here."
                    : "Try another date or check the Appointments tab for your full list."
                }
                action={
                  scheduleIsToday ? (
                    <button type="button" className="dp-btn dp-btn--outline dp-btn--sm" onClick={() => setActiveTab("slots")}>
                      Set up availability
                    </button>
                  ) : (
                    <button type="button" className="dp-btn dp-btn--outline dp-btn--sm" onClick={() => setActiveTab("appointments")}>
                      View all appointments
                    </button>
                  )
                }
              />
            ) : (
              <div className="dp-timeline">
                {scheduleAppts.map((a) => {
                  const done = a.status === "completed";
                  const isCurrent =
                    scheduleIsToday && a.appointment_id === currentApptId && !done && !isAppointmentPast(a.date, a.time);
                  const canConduct = canStartConsultation(a.date, a.status);
                  return (
                    <div key={a.appointment_id} className="dp-timeline-item">
                      <div
                        className={`dp-timeline-dot${done ? " dp-timeline-dot--done" : ""}${isCurrent ? " dp-timeline-dot--current" : ""}`}
                      >
                        {done && (
                          <span className="material-symbols-outlined filled-icon" style={{ fontSize: 11, color: "#fff" }}>
                            check
                          </span>
                        )}
                      </div>
                      <p className="dp-timeline-time">{formatDoctorTime(a.time)}</p>
                      <div
                        role="button"
                        tabIndex={0}
                        className={`dp-timeline-card${isCurrent ? " dp-timeline-card--current" : ""}`}
                        onClick={() => openPatient(a.patient_id)}
                        onKeyDown={(e) => e.key === "Enter" && openPatient(a.patient_id)}
                      >
                        {isCurrent && <span className="dp-badge-current">CURRENT VISIT</span>}
                        <p className="dp-timeline-name">{a.patient_name}</p>
                        <p className="dp-timeline-meta">
                          {done ? (
                            <span className="dp-status-done">Completed</span>
                          ) : (
                            <>Status: {a.status} · Click to open chart</>
                          )}
                        </p>
                        {canConduct && (
                          <Link
                            to={`/doctor/consultation/${a.appointment_id}`}
                            className="dp-btn dp-btn--primary dp-btn--sm dp-timeline-consult-btn"
                            onClick={(e) => e.stopPropagation()}
                          >
                            Start consultation
                          </Link>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </section>

          <section className="dp-panel">
            <div className="dp-panel-head">
              <h2 className="dp-panel-title">Priority queue</h2>
              <button type="button" className="dp-link" onClick={() => setActiveTab("patients")}>
                All patients →
              </button>
            </div>
            <p className="dp-panel-desc">{priorityQueueDesc}</p>
            {urgentQueue.length === 0 ? (
              <EmptyBlock icon="check_circle" title="All caught up" desc="No urgent items in your queue right now." />
            ) : (
              <div className="dp-queue-list">
                {urgentQueue.map((item) => (
                  <article key={item.patientId} className="dp-queue-card">
                    <div className="dp-queue-top">
                      <div className="dp-avatar">{patientInitials(item.name)}</div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <p className="dp-queue-name">{item.name}</p>
                        <p className="dp-queue-meta">{item.meta}</p>
                        <div className="dp-tags">
                          {item.tags.map((t) => (
                            <span key={t.label} className={`dp-tag dp-tag--${t.variant}`}>
                              {t.label}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                    <ClinicalSummaryPanel
                      summaryText={queueSummaries[item.patientId] || item.summary}
                      consult={queueConsult[item.patientId]}
                      variant="list"
                      title="AI Clinical Summary"
                      loading={(queueSummaries[item.patientId] || item.summary) === "Loading clinical summary…"}
                    />
                    <div className="dp-queue-actions">
                      <button type="button" className="dp-btn dp-btn--primary" onClick={() => openPatient(item.patientId)}>
                        <span className="material-symbols-outlined">folder_open</span>
                        Open chart
                      </button>
                      <button type="button" className="dp-btn dp-btn--ghost" onClick={() => openPatient(item.patientId)}>
                        <span className="material-symbols-outlined">call</span>
                        Call
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </div>
      )}

      {activeTab === "refills" && (
        <section className="dp-panel" id="refills">
          <div className="dp-panel-head">
            <h2 className="dp-panel-title">Prescription refills</h2>
            <button type="button" className="dp-btn dp-btn--ghost dp-btn--sm" onClick={() => void loadRefills()} disabled={refillLoading}>
              <span className="material-symbols-outlined">refresh</span>
              Refresh
            </button>
          </div>
          <p className="dp-panel-desc">
            Approve so the patient can pick up at pharmacy, or deny with a note they will see in the app.
          </p>
          {refillLoading ? (
            <RefillTableSkeleton rows={4} />
          ) : pendingRefills.length === 0 ? (
            <EmptyBlock icon="medication" title="No pending refills" desc="Refill requests from patients will show up here." />
          ) : (
            <div className="dp-table-wrap">
              <table className="dp-table">
                <thead>
                  <tr>
                    <th>Patient</th>
                    <th>Medication</th>
                    <th>Requested</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingRefills.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <button type="button" className="dp-link" onClick={() => openPatient(r.patient_id)}>
                          {r.patient_name}
                        </button>
                      </td>
                      <td>
                        <strong>{r.medication_name}</strong>
                        {r.medication_dosage && ` · ${r.medication_dosage}`}
                        {r.medication_frequency && ` · ${r.medication_frequency}`}
                      </td>
                      <td style={{ color: "var(--dp-on-surface-variant)" }}>
                        {r.requested_at ? new Date(r.requested_at).toLocaleString() : "—"}
                      </td>
                      <td>
                        <div className="dp-btn-group">
                          <button type="button" className="dp-btn dp-btn--success dp-btn--sm" onClick={() => void approveRefill(r.id)}>
                            Approve
                          </button>
                          <button type="button" className="dp-btn dp-btn--danger dp-btn--sm" onClick={() => setDenyTarget(r)}>
                            Deny
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {activeTab === "patients" && (
        <section className="dp-panel" id="patients">
          <div className="dp-panel-head">
            <h2 className="dp-panel-title">My patients</h2>
            <span style={{ fontSize: "0.85rem", color: "var(--dp-on-surface-variant)" }}>
              {filteredPatients.length} of {patients.length}
            </span>
          </div>
          {search && (
            <p className="dp-panel-desc">
              Showing results for &ldquo;<strong>{search}</strong>&rdquo;
            </p>
          )}
          {filteredPatients.length === 0 ? (
            <EmptyBlock
              icon="group_off"
              title={search ? "No matches" : "No patients yet"}
              desc={search ? "Try a different name." : "Patients appear here after they book with you."}
            />
          ) : (
            <div className="dp-table-wrap">
              <table className="dp-table">
                <thead>
                  <tr>
                    <th>Patient</th>
                    <th>Case ID</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredPatients.map((p) => (
                    <tr key={p.patient_id}>
                      <td>
                        <div className="dp-table-patient">
                          <div className="dp-avatar dp-avatar--sm">{patientInitials(p.name)}</div>
                          {p.name}
                        </div>
                      </td>
                      <td style={{ color: "var(--dp-on-surface-variant)" }}>{patientCaseId(p.patient_id)}</td>
                      <td>
                        <button type="button" className="dp-btn dp-btn--primary dp-btn--sm" onClick={() => openPatient(p.patient_id)}>
                          Open chart
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {activeTab === "history" && (
        <section className="dp-panel dp-consult-history-panel">
          <div className="dp-panel-head">
            <div>
              <h2 className="dp-panel-title">Consultation history</h2>
              <p className="dp-panel-desc" style={{ margin: "8px 0 0" }}>
                All patients you have seen — symptoms at triage, medications on file, and treatment notes.
              </p>
            </div>
            <span style={{ fontSize: "0.85rem", color: "var(--dp-on-surface-variant)" }}>
              {consultationHistory.length} visit{consultationHistory.length !== 1 ? "s" : ""}
            </span>
          </div>
          <DoctorConsultationHistory
            records={consultationHistory}
            loading={historyLoading}
            onOpenPatient={openPatient}
            onMarkCompleted={markAppointmentCompleted}
            onMarkCancelled={markAppointmentCancelled}
          />
        </section>
      )}

      {activeTab === "appointments" && (
        <section className="dp-panel">
          <div className="dp-panel-head">
            <h2 className="dp-panel-title">All appointments</h2>
            <span style={{ fontSize: "0.85rem", color: "var(--dp-on-surface-variant)" }}>{appointments.length} total</span>
          </div>
          {appointments.length === 0 ? (
            <EmptyBlock icon="calendar_month" title="No appointments" desc="Your full appointment list will appear here." />
          ) : (
            <DoctorAppointmentsSections
              appointments={appointments}
              showPatient
              onViewPatient={openPatient}
            />
          )}
        </section>
      )}

      {activeTab === "slots" && (
        <section className="dp-panel dp-availability-panel" id="availability">
          <div className="dp-availability-hero">
            <div>
              <h2 className="dp-availability-hero-title">Booking availability</h2>
              <p className="dp-availability-hero-desc">
                Manage when patients can book with you. Default slots are created automatically for new doctors.
              </p>
            </div>
            <button
              type="button"
              className="dp-btn dp-btn--primary"
              onClick={() => void seedSlots()}
              disabled={seedingSlots}
            >
              <span className="material-symbols-outlined">add</span>
              {seedingSlots ? "Adding slots…" : "Add 14-day slots"}
            </button>
          </div>
          {bookableSlots.length === 0 ? (
            <EmptyBlock
              icon="schedule"
              title="No open slots"
              desc="Add default slots so patients can book appointments with you."
              action={
                <button type="button" className="dp-btn dp-btn--primary" onClick={() => void seedSlots()} disabled={seedingSlots}>
                  Create default slots
                </button>
              }
            />
          ) : (
            <DoctorAvailabilityGrid slots={bookableSlots} onSeedSlots={() => void seedSlots()} seeding={seedingSlots} />
          )}
        </section>
      )}

      {denyTarget && (
        <div className="dp-modal-backdrop" onClick={() => setDenyTarget(null)}>
          <div className="dp-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Deny refill request</h3>
            <p style={{ color: "var(--dp-on-surface-variant)", margin: "0 0 16px", fontSize: "0.9rem" }}>
              <strong>{denyTarget.patient_name}</strong> — {denyTarget.medication_name} {denyTarget.medication_dosage || ""}
            </p>
            <div className="dp-form-row">
              <label htmlFor="deny-reason">Message to patient</label>
              <textarea
                id="deny-reason"
                rows={4}
                value={denyReason}
                onChange={(e) => setDenyReason(e.target.value)}
                placeholder="Explain why the refill cannot be approved right now…"
              />
            </div>
            <div className="dp-form-actions">
              <button type="button" className="dp-btn dp-btn--ghost" onClick={() => setDenyTarget(null)}>
                Cancel
              </button>
              <button type="button" className="dp-btn dp-btn--danger" onClick={() => void submitDeny()}>
                Deny refill
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
