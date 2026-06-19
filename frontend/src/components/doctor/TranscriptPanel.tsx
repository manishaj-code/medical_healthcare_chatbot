import { useCallback, useEffect, useRef, useState } from "react";
import { useConsultationTranscript } from "../../hooks/useConsultationTranscript";
import { useDeepgramLiveCapture } from "../../hooks/useDeepgramLiveCapture";
import { useTranscriptCapture } from "../../hooks/useTranscriptCapture";
import { useVideoRoom } from "../../modules/video/hooks/useVideoRoom";
import type { TranscriptAiSuggestions } from "../../types/consultationTranscript";
import TranscriptSummaryCard from "./TranscriptSummaryCard";

interface Props {
  appointmentId: string;
  roomId?: string;
  visible: boolean;
  onAnalyzeComplete?: (suggestions: TranscriptAiSuggestions) => void;
}

function providerLabel(provider: string | undefined): string {
  if (provider === "deepgram_live") return "Deepgram live";
  if (provider === "deepgram") return "Deepgram";
  return "Groq Whisper";
}

export default function TranscriptPanel({
  appointmentId,
  roomId,
  visible,
  onAnalyzeComplete,
}: Props) {
  const { connectionState } = useVideoRoom();
  const feedRef = useRef<HTMLDivElement>(null);
  const [interimLine, setInterimLine] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<TranscriptAiSuggestions | null>(null);
  const {
    session,
    sttConfig,
    segments,
    loading,
    analyzing,
    error,
    warning,
    captureError,
    listening,
    start,
    uploadChunk,
    postSegment,
    analyze,
  } = useConsultationTranscript(appointmentId, true);
  const startedRef = useRef(false);
  const [captureStatus, setCaptureStatus] = useState("");

  const provider = sttConfig?.provider ?? "groq";
  const useLiveDeepgram =
    provider === "deepgram_live" &&
    sttConfig?.deepgram?.token_type === "api_key" &&
    Boolean(sttConfig?.deepgram?.token);
  const chunkMs = sttConfig?.chunk_interval_ms ?? 6_000;

  const sessionReady = session?.status === "active";

  useEffect(() => {
    if (!visible || connectionState !== "connected" || startedRef.current) return;
    startedRef.current = true;
    void start(roomId);
  }, [visible, connectionState, roomId, start]);

  const captureEnabled =
    visible && connectionState === "connected" && sessionReady && !loading;

  const handleChunk = useCallback(
    async (blob: Blob, speakerRole: string, speakerLabel: string) => {
      await uploadChunk(blob, speakerRole, speakerLabel);
    },
    [uploadChunk],
  );

  const handleLiveFinal = useCallback(
    async (text: string, speakerRole: string, speakerLabel: string, confidence?: number) => {
      setInterimLine(null);
      await postSegment(text, speakerRole, speakerLabel, confidence);
    },
    [postSegment],
  );

  const handleLiveInterim = useCallback((text: string, _role: string, label: string) => {
    setInterimLine(`${label}: ${text}`);
  }, []);

  const { sourceCount } = useTranscriptCapture(
    captureEnabled && !useLiveDeepgram,
    handleChunk,
    chunkMs,
  );

  useEffect(() => {
    if (!captureEnabled) {
      setCaptureStatus("");
      return;
    }
    if (sourceCount === 0) {
      setCaptureStatus("Waiting for microphone audio… Unmute your mic in the call.");
    } else {
      setCaptureStatus(`Listening to ${sourceCount} audio source${sourceCount === 1 ? "" : "s"}…`);
    }
  }, [captureEnabled, sourceCount]);

  useDeepgramLiveCapture(
    captureEnabled && useLiveDeepgram,
    sttConfig,
    handleLiveFinal,
    handleLiveInterim,
  );

  useEffect(() => {
    const feed = feedRef.current;
    if (!feed) return;
    feed.scrollTop = feed.scrollHeight;
  }, [segments.length, interimLine]);

  const handleAnalyze = async () => {
    const data = await analyze();
    if (data) setSuggestions(data);
  };
  const captureHint = useLiveDeepgram
    ? "Streaming via Deepgram — lines appear as you speak."
    : `Per-speaker capture via ${providerLabel(provider)} · updates every ~${Math.round(chunkMs / 1000)}s`;

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
            {session?.status === "active" ? captureHint : "Transcript session"}
          </p>
        </div>
        <button
          type="button"
          className="dp-btn dp-btn--sm dp-btn--primary"
          disabled={analyzing || segments.length === 0}
          onClick={() => void handleAnalyze()}
        >
          <span className="material-symbols-outlined">auto_awesome</span>
          {analyzing ? "Analyzing…" : "Analyze"}
        </button>
      </header>

      {loading && <p className="video-transcript-muted">Starting transcript…</p>}
      {captureStatus && <p className="video-transcript-muted">{captureStatus}</p>}
      {listening && <p className="video-transcript-muted">Transcribing audio…</p>}
      {warning && <p className="video-transcript-warning">{warning}</p>}
      {captureError && <p className="aura-chat-error">{captureError}</p>}
      {error && <p className="aura-chat-error">{error}</p>}

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
        {segments.length === 0 && !loading && !interimLine && !error && (
          <p className="video-transcript-muted">
            {session?.status === "active"
              ? "Listening… speak clearly with your mic on. First lines appear after a few seconds."
              : "Start the video call and enable live transcript."}
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
        {interimLine && (
          <p className="video-transcript-muted video-transcript-interim">{interimLine}…</p>
        )}
      </div>
    </aside>
  );
}
