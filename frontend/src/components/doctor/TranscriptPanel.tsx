import { useCallback, useEffect, useRef, useState } from "react";
import { useConsultationTranscript } from "../../hooks/useConsultationTranscript";
import { useTranscriptCapture } from "../../hooks/useTranscriptCapture";
import { useVideoRoom } from "../../modules/video/hooks/useVideoRoom";
import {
  formatTranscriptChunkBytes,
  TRANSCRIPT_CHUNK_BYTES_DEFAULT,
} from "../../modules/video/utils/audioTracks";
import type { TranscriptAiSuggestions } from "../../types/consultationTranscript";
import TranscriptSummaryCard from "./TranscriptSummaryCard";

interface Props {
  appointmentId: string;
  roomId?: string;
  visible: boolean;
  onAnalyzeComplete?: (suggestions: TranscriptAiSuggestions) => void;
}

export default function TranscriptPanel({
  appointmentId,
  roomId,
  visible,
  onAnalyzeComplete,
}: Props) {
  const { connectionState } = useVideoRoom();
  const feedRef = useRef<HTMLDivElement>(null);
  const [suggestions, setSuggestions] = useState<TranscriptAiSuggestions | null>(null);
  const {
    session,
    sttConfig,
    segments,
    loading,
    analyzing,
    error,
    captureError,
    listening,
    pendingUploads,
    chunksSent,
    lastChunkStatus,
    start,
    stop,
    uploadChunk,
    analyze,
    sessionReady,
  } = useConsultationTranscript(appointmentId, visible && connectionState === "connected");
  const [captureStatus, setCaptureStatus] = useState("");

  const chunkBytes = sttConfig?.chunk_bytes ?? TRANSCRIPT_CHUNK_BYTES_DEFAULT;
  const chunkSizeLabel = formatTranscriptChunkBytes(chunkBytes);
  const sttReady = Boolean(sttConfig?.available) && !sttConfig?.error;
  const connectStartRef = useRef<string | null>(null);
  const wasConnectedRef = useRef(false);

  useEffect(() => {
    if (!visible || connectionState !== "connected") {
      if (connectionState !== "connected") connectStartRef.current = null;
      return;
    }
    if (sessionReady) return;
    const key = `${appointmentId}:${roomId ?? ""}`;
    if (connectStartRef.current === key) return;
    connectStartRef.current = key;
    void start(roomId);
  }, [visible, connectionState, appointmentId, roomId, sessionReady, start]);

  useEffect(() => {
    if (connectionState === "connected") {
      wasConnectedRef.current = true;
      return;
    }
    if (
      wasConnectedRef.current &&
      connectionState !== "connecting" &&
      connectionState !== "reconnecting" &&
      sessionReady
    ) {
      wasConnectedRef.current = false;
      void stop();
    }
  }, [connectionState, sessionReady, stop]);

  useEffect(() => () => void stop(), [stop]);

  const captureEnabled =
    visible && connectionState === "connected" && sessionReady && !loading && sttReady;

  const handleChunk = useCallback(
    (blob: Blob, speakerRole: string, speakerLabel: string) => {
      uploadChunk(blob, speakerRole, speakerLabel);
    },
    [uploadChunk],
  );

  const { sourceCount } = useTranscriptCapture(captureEnabled, handleChunk, chunkBytes);

  useEffect(() => {
    if (!captureEnabled) {
      setCaptureStatus("");
      return;
    }
    if (sourceCount === 0) {
      setCaptureStatus(
        "Waiting for call audio — ensure the patient has joined and both mics are unmuted.",
      );
    } else {
      setCaptureStatus(
        `Capturing ${sourceCount} speaker${sourceCount === 1 ? "" : "s"} · ~${chunkSizeLabel} per chunk`,
      );
    }
  }, [captureEnabled, sourceCount, chunkSizeLabel]);

  useEffect(() => {
    const feed = feedRef.current;
    if (!feed) return;
    feed.scrollTop = feed.scrollHeight;
  }, [segments.length]);

  const handleAnalyze = async () => {
    const data = await analyze();
    if (data) setSuggestions(data);
  };

  return (
    <aside
      className={`video-transcript-panel${visible ? "" : " video-transcript-panel--hidden"}`}
      aria-label="Live consultation transcript"
      aria-hidden={!visible}
    >
      <header className="video-transcript-panel-head">
        <div>
          <h3>Live transcript</h3>
          <p className="video-transcript-panel-sub">
            {session?.status === "active"
              ? `LiveKit → Deepgram chunk mode · ~${chunkSizeLabel} per speaker`
              : "Transcript session"}
          </p>
        </div>
        <button
          type="button"
          className="dp-btn dp-btn--sm dp-btn--primary"
          disabled={analyzing || segments.length === 0}
          title={
            segments.length === 0
              ? "Wait for at least one transcript line from the call"
              : "Analyze captured transcript with AI"
          }
          onClick={() => void handleAnalyze()}
        >
          <span className="material-symbols-outlined">auto_awesome</span>
          {analyzing ? "Analyzing…" : "Analyze"}
        </button>
      </header>

      {loading && <p className="video-transcript-muted">Starting transcript…</p>}
      {captureStatus && <p className="video-transcript-muted">{captureStatus}</p>}
      {lastChunkStatus && <p className="video-transcript-muted">{lastChunkStatus}</p>}
      {chunksSent > 0 && segments.length === 0 && (
        <p className="video-transcript-muted">Audio sent — waiting for speech recognition…</p>
      )}
      {listening && (
        <p className="video-transcript-muted">
          Transcribing audio
          {pendingUploads > 0 ? ` (${pendingUploads} queued)…` : "…"}
        </p>
      )}
      {captureError && <p className="aura-chat-error">{captureError}</p>}
      {error && (
        <p className="aura-chat-error">
          {error}
          {!sessionReady && (
            <button
              type="button"
              className="dp-btn dp-btn--sm dp-btn--outline"
              style={{ marginLeft: 8 }}
              onClick={() => {
                connectStartRef.current = null;
                void start(roomId);
              }}
            >
              Retry transcript
            </button>
          )}
        </p>
      )}

      {suggestions && (
        <div className="video-transcript-summary-wrap">
          <TranscriptSummaryCard
            suggestions={suggestions}
            onApplyToForm={
              onAnalyzeComplete ? () => onAnalyzeComplete(suggestions) : undefined
            }
            applyLabel="Apply to consultation form"
          />
        </div>
      )}

      <div className="video-transcript-feed" ref={feedRef}>
        {segments.length === 0 && !loading && !error && (
          <p className="video-transcript-muted">
            {session?.status === "active"
              ? `Speak clearly with mics on — first lines appear after ~${chunkSizeLabel} of speech.`
              : "Start the video call to enable live transcript."}
          </p>
        )}
        {segments.map((seg) => (
          <article
            key={seg.id}
            className={`video-transcript-line video-transcript-line--${seg.speaker_role}`}
          >
            <span className="video-transcript-speaker">{seg.speaker_label || seg.speaker_role}</span>
            <p>{seg.text}</p>
          </article>
        ))}
      </div>
    </aside>
  );
}
