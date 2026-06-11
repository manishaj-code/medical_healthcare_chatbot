import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";

interface Analytics {
  total_users: number;
  total_patients: number;
  total_doctors: number;
  total_appointments: number;
  total_conversations: number;
  total_assessments: number;
}

interface PatientRow {
  id: string;
  user_id: string;
  name: string;
  email: string;
  created_at: string | null;
  appointments_count: number;
  reports_count: number;
  conversations_count: number;
}

interface DoctorRow {
  id: string;
  user_id: string;
  name: string;
  email: string;
  specialty: string | null;
  experience_years: number;
  rating: number;
  is_verified: boolean;
  appointments_count: number;
}

interface AuditLogRow {
  action: string;
  status: number;
  at: string;
}

interface EmailStatus {
  smtp_configured: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_from: string;
}

type AdminTab = "patients" | "doctors" | "data";

export default function AdminPanel() {
  const [tab, setTab] = useState<AdminTab>("patients");
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [patients, setPatients] = useState<PatientRow[]>([]);
  const [doctors, setDoctors] = useState<DoctorRow[]>([]);
  const [logs, setLogs] = useState<AuditLogRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [emailStatus, setEmailStatus] = useState<EmailStatus | null>(null);
  const [testEmail, setTestEmail] = useState("");
  const [testOtp, setTestOtp] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [overview, patientRows, doctorRows, auditRows, smtpStatus] = await Promise.all([
        api<Analytics>("/api/v1/admin/analytics/overview"),
        api<PatientRow[]>("/api/v1/admin/patients"),
        api<DoctorRow[]>("/api/v1/admin/doctors"),
        api<AuditLogRow[]>("/api/v1/admin/audit-logs"),
        api<EmailStatus>("/api/v1/admin/email/status"),
      ]);
      setAnalytics(overview);
      setPatients(patientRows);
      setDoctors(doctorRows);
      setLogs(auditRows);
      setEmailStatus(smtpStatus);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load admin data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const deletePatient = async (row: PatientRow) => {
    if (!window.confirm(`Delete patient ${row.name} (${row.email}) and all their data?`)) return;
    setActionLoading(true);
    setMessage("");
    setError("");
    try {
      await api(`/api/v1/admin/patients/${row.id}`, { method: "DELETE" });
      setMessage(`Removed patient ${row.email}.`);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not delete patient");
    } finally {
      setActionLoading(false);
    }
  };

  const deleteDoctor = async (row: DoctorRow) => {
    if (!window.confirm(`Delete doctor ${row.name} (${row.email}) and their availability?`)) return;
    setActionLoading(true);
    setMessage("");
    setError("");
    try {
      await api(`/api/v1/admin/doctors/${row.id}`, { method: "DELETE" });
      setMessage(`Removed doctor ${row.email}.`);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not delete doctor");
    } finally {
      setActionLoading(false);
    }
  };

  const sendTestEmail = async () => {
    const email = testEmail.trim();
    if (!email) {
      setError("Enter an email address for the SMTP test.");
      return;
    }
    setActionLoading(true);
    setMessage("");
    setError("");
    setTestOtp("");
    try {
      const res = await api<{ message: string; mode: string; dev_otp?: string }>(
        "/api/v1/admin/email/test",
        { method: "POST", body: JSON.stringify({ email }) }
      );
      setMessage(res.message);
      if (res.dev_otp) setTestOtp(res.dev_otp);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "SMTP test failed");
    } finally {
      setActionLoading(false);
    }
  };

  const resetData = async (mode: "keep_doctors" | "all_data") => {
    const label =
      mode === "keep_doctors"
        ? "Clear ALL patient records (chats, reports, appointments) and remove patient accounts, but KEEP the doctor catalog?"
        : "Clear ALL patients AND doctors, then re-seed the default doctor catalog? Admin accounts are kept.";
    if (!window.confirm(label)) return;
    if (!window.confirm("This cannot be undone. Continue?")) return;

    setActionLoading(true);
    setMessage("");
    setError("");
    try {
      const res = await api<{ message: string; removed_users: number; doctors_in_catalog: number }>(
        "/api/v1/admin/reset-data",
        { method: "POST", body: JSON.stringify({ mode }) }
      );
      setMessage(`${res.message} Removed ${res.removed_users} user(s). Doctors in catalog: ${res.doctors_in_catalog}.`);
      await load();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className="admin-panel">
      <div className="admin-panel-head">
        <div>
          <h1>Admin Panel</h1>
          <p className="admin-panel-sub">Manage patients, doctors, and platform data.</p>
        </div>
        <button type="button" className="btn btn-outline" onClick={() => void load()} disabled={loading || actionLoading}>
          Refresh
        </button>
      </div>

      {analytics && (
        <div className="stats admin-stats">
          <div className="stat-card"><h3>{analytics.total_patients}</h3><p>Patients</p></div>
          <div className="stat-card"><h3>{analytics.total_doctors}</h3><p>Doctors</p></div>
          <div className="stat-card"><h3>{analytics.total_appointments}</h3><p>Appointments</p></div>
          <div className="stat-card"><h3>{analytics.total_conversations}</h3><p>Consultations</p></div>
        </div>
      )}

      {message && <p className="admin-banner admin-banner--ok">{message}</p>}
      {error && <p className="admin-banner admin-banner--error">{error}</p>}

      <div className="admin-tabs">
        <button type="button" className={tab === "patients" ? "admin-tab active" : "admin-tab"} onClick={() => setTab("patients")}>
          Patients ({patients.length})
        </button>
        <button type="button" className={tab === "doctors" ? "admin-tab active" : "admin-tab"} onClick={() => setTab("doctors")}>
          Doctors ({doctors.length})
        </button>
        <button type="button" className={tab === "data" ? "admin-tab active" : "admin-tab"} onClick={() => setTab("data")}>
          Data reset
        </button>
      </div>

      {loading && <p className="muted-text">Loading...</p>}

      {!loading && tab === "patients" && (
        <div className="card admin-card">
          <h3>Patient accounts</h3>
          <p className="admin-card-hint">Delete removes the patient, chats, reports, appointments, and profile data.</p>
          {patients.length === 0 ? (
            <p className="muted-text">No patient accounts.</p>
          ) : (
            <div className="admin-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Chats</th>
                    <th>Reports</th>
                    <th>Appointments</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {patients.map((row) => (
                    <tr key={row.id}>
                      <td>{row.name}</td>
                      <td>{row.email}</td>
                      <td>{row.conversations_count}</td>
                      <td>{row.reports_count}</td>
                      <td>{row.appointments_count}</td>
                      <td>
                        <button
                          type="button"
                          className="admin-danger-btn"
                          disabled={actionLoading}
                          onClick={() => void deletePatient(row)}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {!loading && tab === "doctors" && (
        <div className="card admin-card">
          <h3>Doctor accounts</h3>
          <p className="admin-card-hint">Delete removes the doctor account, availability slots, and linked appointments.</p>
          {doctors.length === 0 ? (
            <p className="muted-text">No doctor accounts.</p>
          ) : (
            <div className="admin-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Email</th>
                    <th>Specialty</th>
                    <th>Rating</th>
                    <th>Appointments</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {doctors.map((row) => (
                    <tr key={row.id}>
                      <td>{row.name}</td>
                      <td>{row.email}</td>
                      <td>{row.specialty || "—"}</td>
                      <td>{row.rating.toFixed(1)}</td>
                      <td>{row.appointments_count}</td>
                      <td>
                        <button
                          type="button"
                          className="admin-danger-btn"
                          disabled={actionLoading}
                          onClick={() => void deleteDoctor(row)}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {!loading && tab === "data" && (
        <div className="admin-reset-grid">
          <div className="card admin-card">
            <h3>SMTP email test</h3>
            <p>
              Sends a sample chat verification email using the same OTP email path as guest chat
              ({emailStatus?.smtp_configured ? "SMTP configured" : "console mode — OTP logged on server"}).
            </p>
            {emailStatus && (
              <ul className="admin-email-status">
                <li><strong>Host:</strong> {emailStatus.smtp_host || "—"}</li>
                <li><strong>Port:</strong> {emailStatus.smtp_port}</li>
                <li><strong>From:</strong> {emailStatus.smtp_from}</li>
              </ul>
            )}
            <div className="admin-email-test-form">
              <input
                type="email"
                className="admin-email-input"
                placeholder="recipient@example.com"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
                disabled={actionLoading}
              />
              <button
                type="button"
                className="btn btn-primary"
                disabled={actionLoading}
                onClick={() => void sendTestEmail()}
              >
                Send sample OTP email
              </button>
            </div>
            {testOtp && (
              <p className="admin-email-dev-otp">
                Dev sample code: <code>{testOtp}</code>
              </p>
            )}
          </div>
          <div className="card admin-card">
            <h3>Truncate patient data (keep doctors)</h3>
            <p>
              Removes all patients and operational records: consultations, reports, appointments,
              medical history, tokens, and audit logs. The seeded doctor catalog stays intact.
            </p>
            <button
              type="button"
              className="admin-danger-btn admin-danger-btn--block"
              disabled={actionLoading}
              onClick={() => void resetData("keep_doctors")}
            >
              Clear patients &amp; keep doctors
            </button>
          </div>
          <div className="card admin-card">
            <h3>Truncate all (patients + doctors)</h3>
            <p>
              Removes all patient and doctor accounts, then re-seeds the default 5 doctors
              (e.g. dr.sharma@clinic.com / Doctor@12345). Admin accounts are not removed.
            </p>
            <button
              type="button"
              className="admin-danger-btn admin-danger-btn--block"
              disabled={actionLoading}
              onClick={() => void resetData("all_data")}
            >
              Reset everything &amp; re-seed doctors
            </button>
          </div>
        </div>
      )}

      <div className="card admin-card" style={{ marginTop: "1.5rem" }}>
        <h3>Recent audit logs</h3>
        <div className="admin-table-wrap">
          <table>
            <thead>
              <tr><th>Action</th><th>Status</th><th>Time</th></tr>
            </thead>
            <tbody>
              {logs.slice(0, 15).map((l, i) => (
                <tr key={i}>
                  <td style={{ fontSize: "0.85rem" }}>{l.action}</td>
                  <td>{l.status}</td>
                  <td style={{ fontSize: "0.8rem" }}>{l.at}</td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr><td colSpan={3} className="muted-text">No audit logs yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
