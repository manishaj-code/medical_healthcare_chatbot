import { useEffect, useRef, useState } from "react";
import TranscriptPanel from "./doctor/TranscriptPanel";
import { VideoModalSkeleton } from "./skeleton";
import { VideoProvider } from "../modules/video/context/VideoProvider";
import { VideoRoom } from "../modules/video/components/VideoRoom";
import { api } from "../api/client";
import {
  getSharedLiveKitService,
  releaseSharedLiveKitService,
} from "../modules/video/services/sharedLiveKit";
import type { VideoConsultationSession, VideoParticipantRole } from "../types/videoConsultation";
import type { TranscriptAiSuggestions } from "../types/consultationTranscript";

interface Props {
  open: boolean;
  loading: boolean;
  error: string;
  session: VideoConsultationSession | null;
  role?: VideoParticipantRole;
  appointmentId?: string;
  onClose: () => void;
  onTranscriptAnalyze?: (suggestions: TranscriptAiSuggestions) => void;
}

export default function VideoCallModal({
  open,
  loading,
  error,
  session,
  role = "patient",
  appointmentId,
  onClose,
  onTranscriptAnalyze,
}: Props) {
  const [transcriptOpen, setTranscriptOpen] = useState(true);
  const wasOpenRef = useRef(false);

  useEffect(() => {
    if (!open) {
      void releaseSharedLiveKitService();
      if (wasOpenRef.current && role === "doctor" && appointmentId) {
        void api(
          `/api/v1/doctor/appointments/${appointmentId}/transcript/stop`,
          { method: "POST" },
        ).catch(() => undefined);
      }
      wasOpenRef.current = false;
      return;
    }
    wasOpenRef.current = true;
    if (role === "doctor") {
      setTranscriptOpen(true);
    }
  }, [open, role, appointmentId]);

  if (!open) {
    return null;
  }

  const service = getSharedLiveKitService();
  const hasSession = Boolean(session?.token?.trim() && session?.url?.trim());
  const waitingFor = role === "doctor" ? "patient" : "doctor";
  const canTranscript = role === "doctor" && Boolean(appointmentId);
  const splitLayout = canTranscript && transcriptOpen;

  return (
    <div className="video-call-modal-backdrop" role="presentation">
      <div
        className={`video-call-modal${splitLayout ? " video-call-modal--with-transcript" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="video-call-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="video-call-modal-header">
          <div>
            <h2 id="video-call-modal-title">Video consultation</h2>
            {session?.room_id && (
              <p className="video-call-modal-sub">Room {session.room_id}</p>
            )}
            {role === "patient" && session?.doctor_name && (
              <p className="video-call-modal-sub">With Dr. {session.doctor_name}</p>
            )}
            {role === "doctor" && session?.patient_name && (
              <p className="video-call-modal-sub">Patient: {session.patient_name}</p>
            )}
            {session?.apt_id && (
              <p className="video-call-modal-sub">Appointment {session.apt_id}</p>
            )}
          </div>
          <div className="video-call-modal-header-actions">
            {canTranscript && (
              <button
                type="button"
                className={`video-transcript-toggle${transcriptOpen ? " video-transcript-toggle--on" : " video-transcript-toggle--off"}`}
                onClick={() => setTranscriptOpen((v) => !v)}
                aria-pressed={transcriptOpen}
                title={transcriptOpen ? "Turn live transcript off" : "Turn live transcript on"}
              >
                <span className="material-symbols-outlined" aria-hidden>
                  {transcriptOpen ? "closed_caption" : "closed_caption_disabled"}
                </span>
                <span className="video-transcript-toggle-label">Live transcript</span>
                <span className="video-transcript-toggle-state" aria-hidden>
                  {transcriptOpen ? "ON" : "OFF"}
                </span>
              </button>
            )}
            <button type="button" className="video-call-modal-close" onClick={onClose} aria-label="Close">
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>
        </header>

        <div className={`video-call-modal-body${splitLayout ? " video-call-modal-body--split" : ""}`}>
          {loading && !hasSession && <VideoModalSkeleton />}
          {!loading && error && <p className="aura-chat-error">{error}</p>}
          {!loading && !error && !hasSession && (
            <p className="pd-muted">No video session available. Check LiveKit settings on the API.</p>
          )}
          {hasSession && session && (
            <VideoProvider
              service={service}
              token={session.token}
              url={session.url}
              roomId={session.room_id}
              autoJoin
            >
              <div className="video-call-modal-stage">
                {loading && <p className="video-call-connecting-overlay">Refreshing connection…</p>}
                <VideoRoom
                  token={session.token}
                  url={session.url}
                  compact
                  showLocalPreview
                  waitingFor={waitingFor}
                  onLeave={onClose}
                />
              </div>
              {canTranscript && appointmentId && (
                <TranscriptPanel
                  appointmentId={appointmentId}
                  roomId={session.room_id}
                  visible={transcriptOpen}
                  onAnalyzeComplete={onTranscriptAnalyze}
                />
              )}
            </VideoProvider>
          )}
        </div>
      </div>
    </div>
  );
}
