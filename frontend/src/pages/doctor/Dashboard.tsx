import { useEffect, useState } from "react";
import { api } from "../../api/client";

interface Appointment {
  appointment_id: string;
  patient_id: string;
  patient_name: string;
  date: string;
  time: string;
  status: string;
}

interface Patient {
  patient_id: string;
  name: string;
}

interface PatientDetail {
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

function formatTime(t: string): string {
  const parts = t.split(":");
  if (parts.length < 2) return t;
  const h = parseInt(parts[0], 10);
  const m = parts[1];
  const ampm = h >= 12 ? "PM" : "AM";
  const hour = h % 12 || 12;
  return `${hour}:${m.slice(0, 2)} ${ampm}`;
}

export default function DoctorDashboard() {
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  const [patientDetail, setPatientDetail] = useState<PatientDetail | null>(null);
  const [conversations, setConversations] = useState<PatientConversation[]>([]);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [tab, setTab] = useState<"summary" | "chats">("summary");
  const [mySlots, setMySlots] = useState<{ date: string; time: string }[]>([]);
  const [refillRequests, setRefillRequests] = useState<RefillRequest[]>([]);
  const [refillLoading, setRefillLoading] = useState(false);
  const [denyTarget, setDenyTarget] = useState<RefillRequest | null>(null);
  const [denyReason, setDenyReason] = useState("Please schedule a follow-up visit before refilling.");

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

  useEffect(() => {
    api<Appointment[]>("/api/v1/doctor/appointments").then(setAppointments).catch(console.error);
    api<Patient[]>("/api/v1/doctor/patients").then(setPatients).catch(console.error);
    api<{ date: string; time: string }[]>("/api/v1/doctor/availability").then(setMySlots).catch(console.error);
    void loadRefills();
  }, []);

  const seedSlots = async () => {
    await api("/api/v1/doctor/availability/seed-default", { method: "POST" });
    const slots = await api<{ date: string; time: string }[]>("/api/v1/doctor/availability");
    setMySlots(slots);
    alert("Default availability slots created for the next 14 days.");
  };

  const openPatient = async (patientId: string) => {
    setSelectedPatientId(patientId);
    setLoadingDetail(true);
    setTab("summary");
    try {
      const [detail, chats] = await Promise.all([
        api<PatientDetail>(`/api/v1/doctor/patients/${patientId}`),
        api<PatientConversation[]>(`/api/v1/doctor/patients/${patientId}/conversations`),
      ]);
      setPatientDetail(detail);
      setConversations(chats);
    } catch (err) {
      console.error(err);
      setPatientDetail(null);
      setConversations([]);
    } finally {
      setLoadingDetail(false);
    }
  };

  const closePatient = () => {
    setSelectedPatientId(null);
    setPatientDetail(null);
    setConversations([]);
  };

  const todayAppts = appointments.filter((a) => {
    const today = new Date().toISOString().slice(0, 10);
    return a.date === today;
  });

  const pendingRefills = refillRequests.filter((r) => r.status === "pending");

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

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
        <h1 style={{ margin: 0 }}>Doctor Dashboard</h1>
        <span className="muted-text">Dr. {localStorage.getItem("user_name") || "Doctor"}</span>
      </div>

      <div className="card refill-requests-card" style={{ marginBottom: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
          <h3 style={{ margin: 0 }}>Prescription refill requests ({pendingRefills.length} pending)</h3>
          <button type="button" className="btn btn-outline" onClick={() => void loadRefills()} disabled={refillLoading}>
            Refresh
          </button>
        </div>
        <p className="muted-text" style={{ fontSize: "0.85rem", marginTop: 0 }}>
          Review patient refill requests here. Approve to notify the patient they can pick up at pharmacy, or deny with a reason.
        </p>
        {refillLoading && <p className="muted-text">Loading refill requests...</p>}
        {!refillLoading && pendingRefills.length === 0 && (
          <p className="muted-text">No pending refill requests.</p>
        )}
        {!refillLoading && pendingRefills.length > 0 && (
          <table>
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
                  <td>{r.patient_name}</td>
                  <td>
                    {r.medication_name} {r.medication_dosage || ""}
                    {r.medication_frequency ? ` · ${r.medication_frequency}` : ""}
                  </td>
                  <td>{r.requested_at ? new Date(r.requested_at).toLocaleString() : "—"}</td>
                  <td style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <button type="button" className="btn btn-primary" style={{ fontSize: "0.8rem" }} onClick={() => void approveRefill(r.id)}>
                      Approve
                    </button>
                    <button type="button" className="btn btn-outline" style={{ fontSize: "0.8rem" }} onClick={() => setDenyTarget(r)}>
                      Deny
                    </button>
                    <button type="button" className="btn btn-outline" style={{ fontSize: "0.8rem" }} onClick={() => openPatient(r.patient_id)}>
                      View patient
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {refillRequests.some((r) => r.status !== "pending") && (
          <>
            <h4 style={{ marginTop: "1rem" }}>Recent decisions</h4>
            <table>
              <thead>
                <tr><th>Patient</th><th>Medication</th><th>Status</th><th>Reviewed</th></tr>
              </thead>
              <tbody>
                {refillRequests.filter((r) => r.status !== "pending").slice(0, 8).map((r) => (
                  <tr key={r.id}>
                    <td>{r.patient_name}</td>
                    <td>{r.medication_name} {r.medication_dosage || ""}</td>
                    <td><span className={`badge ${r.status === "approved" ? "success" : "danger"}`}>{r.status}</span></td>
                    <td>{r.reviewed_at ? new Date(r.reviewed_at).toLocaleString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>

      <div className="card" style={{ marginBottom: "1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h3 style={{ margin: 0 }}>My Availability ({mySlots.length} open slots)</h3>
          <button className="btn btn-outline" onClick={seedSlots}>Add Default Slots</button>
        </div>
        <p className="muted-text" style={{ fontSize: "0.85rem", marginTop: "0.5rem" }}>
          Patients see your slots when booking via chatbot or Doctors page. New doctors get 14 days of slots on registration.
        </p>
        {mySlots.length > 0 && (
          <div style={{ marginTop: "0.5rem", display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
            {mySlots.slice(0, 12).map((s, i) => (
              <span key={i} className="badge">{s.date} {s.time.slice(0, 5)}</span>
            ))}
            {mySlots.length > 12 && <span className="muted-text">+{mySlots.length - 12} more</span>}
          </div>
        )}
      </div>

      <div className="doctor-grid">
        <div className="card">
          <h3>Today's Appointments ({todayAppts.length})</h3>
          <table>
            <thead>
              <tr><th>Patient</th><th>Time</th><th>Status</th><th></th></tr>
            </thead>
            <tbody>
              {todayAppts.map((a) => (
                <tr key={a.appointment_id}>
                  <td>{a.patient_name}</td>
                  <td>{formatTime(a.time)}</td>
                  <td><span className="badge">{a.status}</span></td>
                  <td>
                    <button className="btn btn-outline" style={{ fontSize: "0.8rem" }} onClick={() => openPatient(a.patient_id)}>
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {todayAppts.length === 0 && <p className="muted-text" style={{ marginTop: "0.5rem" }}>No appointments today.</p>}
        </div>

        <div className="card">
          <h3>My Patients ({patients.length})</h3>
          {patients.map((p) => (
            <div key={p.patient_id} className="doctor-card">
              <span>{p.name}</span>
              <button className="btn btn-outline" onClick={() => openPatient(p.patient_id)}>Patient Details</button>
            </div>
          ))}
          {patients.length === 0 && <p className="muted-text">No patients yet.</p>}
        </div>
      </div>

      <div className="card" style={{ marginTop: "1rem" }}>
        <h3>All My Appointments</h3>
        <table>
          <thead>
            <tr><th>Patient</th><th>Date</th><th>Time</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {appointments.map((a) => (
              <tr key={a.appointment_id}>
                <td>{a.patient_name}</td>
                <td>{a.date}</td>
                <td>{formatTime(a.time)}</td>
                <td><span className="badge">{a.status}</span></td>
                <td>
                  <button className="btn btn-outline" style={{ fontSize: "0.8rem" }} onClick={() => openPatient(a.patient_id)}>
                    Details
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {appointments.length === 0 && <p className="muted-text">No appointments scheduled.</p>}
      </div>

      {denyTarget && (
        <div className="patient-detail-overlay" onClick={() => setDenyTarget(null)}>
          <div className="patient-detail-panel card" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <h3>Deny refill request</h3>
            <p className="muted-text">
              {denyTarget.patient_name} — {denyTarget.medication_name} {denyTarget.medication_dosage || ""}
            </p>
            <label style={{ display: "block", marginTop: "0.75rem", fontSize: "0.9rem" }}>
              Reason (shown to patient)
            </label>
            <textarea
              className="consult-textarea"
              rows={4}
              value={denyReason}
              onChange={(e) => setDenyReason(e.target.value)}
              style={{ width: "100%", marginTop: "0.35rem" }}
            />
            <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem", justifyContent: "flex-end" }}>
              <button type="button" className="btn btn-outline" onClick={() => setDenyTarget(null)}>Cancel</button>
              <button type="button" className="btn btn-primary" onClick={() => void submitDeny()}>Deny refill</button>
            </div>
          </div>
        </div>
      )}

      {selectedPatientId && (
        <div className="patient-detail-overlay" onClick={closePatient}>
          <div className="patient-detail-panel card" onClick={(e) => e.stopPropagation()}>
            <div className="patient-detail-header">
              <h2>{patientDetail?.name || "Patient Details"}</h2>
              <button type="button" className="btn btn-outline" onClick={closePatient}>Close</button>
            </div>

            {loadingDetail && <p className="muted-text">Loading patient data...</p>}

            {!loadingDetail && patientDetail && (
              <>
                <div className="patient-meta">
                  <span><strong>Email:</strong> {patientDetail.email}</span>
                  {patientDetail.dob && <span><strong>DOB:</strong> {patientDetail.dob}</span>}
                  {patientDetail.gender && <span><strong>Gender:</strong> {patientDetail.gender}</span>}
                  {patientDetail.blood_group && <span><strong>Blood:</strong> {patientDetail.blood_group}</span>}
                </div>

                <h4 style={{ marginTop: "1rem" }}>Appointments with you</h4>
                <table>
                  <thead><tr><th>Date</th><th>Time</th><th>Status</th></tr></thead>
                  <tbody>
                    {patientDetail.appointments.map((a) => (
                      <tr key={a.appointment_id}>
                        <td>{a.date}</td>
                        <td>{formatTime(a.time)}</td>
                        <td><span className="badge">{a.status}</span></td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                <div className="detail-tabs">
                  <button
                    type="button"
                    className={tab === "summary" ? "detail-tab active" : "detail-tab"}
                    onClick={() => setTab("summary")}
                  >
                    AI Summary
                  </button>
                  <button
                    type="button"
                    className={tab === "chats" ? "detail-tab active" : "detail-tab"}
                    onClick={() => setTab("chats")}
                  >
                    Chatbot Conversations ({conversations.length})
                  </button>
                </div>

                {tab === "summary" && (
                  <pre className="summary-pre">{patientDetail.summary}</pre>
                )}

                {tab === "chats" && (
                  <div className="doctor-chat-list">
                    {conversations.length === 0 && (
                      <p className="muted-text">No chatbot conversations for this patient yet.</p>
                    )}
                    {conversations.map((conv) => (
                      <div key={conv.conversation_id} className="doctor-conv-block">
                        <div className="doctor-conv-title">
                          {conv.title}
                          {conv.emergency_flag && <span className="badge danger">Emergency</span>}
                          <span className="muted-text" style={{ fontSize: "0.8rem", marginLeft: "0.5rem" }}>
                            {conv.created_at ? new Date(conv.created_at).toLocaleString() : ""}
                          </span>
                        </div>
                        <div className="doctor-conv-messages">
                          {conv.messages.map((m, i) => (
                            <div key={i} className={`doctor-msg ${m.role === "user" ? "user" : "bot"}`}>
                              <strong>{m.role === "user" ? "Patient" : "AI"}:</strong> {m.content}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
