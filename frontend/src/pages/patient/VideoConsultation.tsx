import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../../api/client";
import { VideoConsultSkeleton } from "../../components/skeleton";

export default function VideoConsultation() {
  const { appointmentId } = useParams<{ appointmentId: string }>();
  const [search] = useSearchParams();
  const [joinUrl, setJoinUrl] = useState(search.get("join") || "");
  const [meta, setMeta] = useState<{ apt_id?: string; doctor_name?: string; room_id?: string }>({});
  const [error, setError] = useState("");

  useEffect(() => {
    if (!appointmentId || joinUrl) return;
    api<{
      join_url: string;
      apt_id: string;
      doctor_name?: string;
      room_id: string;
    }>(`/api/v1/appointments/${appointmentId}/video`)
      .then((data) => {
        setJoinUrl(data.join_url);
        setMeta({ apt_id: data.apt_id, room_id: data.room_id });
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Could not load video room.");
      });
  }, [appointmentId, joinUrl]);

  const embedSrc = joinUrl || (meta.room_id ? `https://meet.jit.si/${meta.room_id}` : "");

  return (
    <div className="video-consult-page">
      <div className="video-consult-header">
        <Link to="/appointments" className="pd-outline-btn">← Back to appointments</Link>
        <div>
          <h2>Video Consultation</h2>
          {meta.apt_id && <p className="pd-muted">Appointment {meta.apt_id}</p>}
        </div>
      </div>

      {error && <p className="aura-chat-error">{error}</p>}

      {embedSrc ? (
        <iframe
          title="MediAI video consultation"
          className="video-consult-frame"
          src={embedSrc}
          allow="camera; microphone; fullscreen; display-capture"
        />
      ) : (
        <VideoConsultSkeleton />
      )}
    </div>
  );
}
