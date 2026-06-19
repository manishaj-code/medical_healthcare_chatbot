import { useEffect, useRef } from "react";
import { Link, useParams } from "react-router-dom";
import VideoCallModal from "../../components/VideoCallModal";
import { useVideoConsultation } from "../../hooks/useVideoConsultation";

export default function VideoConsultation() {
  const { appointmentId } = useParams<{ appointmentId: string }>();
  const { session, loading, error, joinAppointment, reset } = useVideoConsultation("patient");
  const joinedRef = useRef(false);

  useEffect(() => {
    if (!appointmentId || joinedRef.current) return;
    joinedRef.current = true;
    void joinAppointment(appointmentId).catch(() => undefined);
  }, [appointmentId, joinAppointment]);

  return (
    <div className="video-consult-page">
      <div className="video-consult-header">
        <Link to="/appointments" className="pd-outline-btn">← Back to appointments</Link>
        <div>
          <h2>Video Consultation</h2>
          {session?.apt_id && <p className="pd-muted">Appointment {session.apt_id}</p>}
        </div>
      </div>

      <VideoCallModal
        open
        loading={loading}
        error={error}
        session={session}
        role="patient"
        onClose={() => {
          reset();
          window.location.href = "/appointments";
        }}
      />
    </div>
  );
}
