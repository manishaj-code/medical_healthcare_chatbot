import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import AppointmentCard, { AppointmentItem } from "../../components/AppointmentCard";
import { AppointmentListSkeleton } from "../../components/skeleton";

export default function PatientAppointments() {
  const [appts, setAppts] = useState<AppointmentItem[]>([]);
  const [loading, setLoading] = useState(true);

  const userName = localStorage.getItem("user_name") || "you";

  const load = useCallback(() => {
    setLoading(true);
    api<AppointmentItem[]>("/api/v1/appointments")
      .then(setAppts)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const refresh = () => load();
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [load]);

  return (
    <div className="patient-dashboard">
      <section className="pd-section pd-appointments pd-appointments-page">
        <div className="pd-section-head pd-appointments-head">
          <div>
            <h3>My Appointments</h3>
            <p className="pd-section-sub">Showing appointments for {userName} only</p>
          </div>
          <button type="button" className="pd-outline-btn" onClick={load} disabled={loading}>
            Refresh
          </button>
        </div>

        {loading ? (
          <AppointmentListSkeleton count={4} />
        ) : appts.length === 0 ? (
          <div className="pd-empty-card">
            <span className="material-symbols-outlined pd-empty-icon">event_busy</span>
            <p>No appointments yet.</p>
            <Link to="/doctors" className="pd-outline-btn">Book a doctor</Link>
          </div>
        ) : (
          <div className="pd-appt-list">
            {appts.map((a) => (
              <AppointmentCard key={a.id} appointment={a} showStatus />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
