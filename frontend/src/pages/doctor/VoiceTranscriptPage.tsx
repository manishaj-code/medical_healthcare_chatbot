import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiUpload } from "../../api/client";
import { captureMicWav } from "../../utils/wavMicCapture";

const RECORD_MS = 6_000;
const MIN_BYTES = 1_400;

type Health = {
  transcript_enabled: boolean;
  provider: string;
  available: boolean;
  model?: string;
  chunk_bytes?: number;
  ffmpeg_available?: boolean;
  error?: string;
};

type TranscribeDebug = {
  input_bytes?: number;
  input_mime?: string;
  processed_bytes?: number;
  processed_mime?: string;
  mean_volume_db?: number;
  wav_header?: {
    sample_rate?: number;
    channels?: number;
    bits?: number;
    duration_sec?: number;
  };
  ffmpeg_used?: boolean;
  ffmpeg_failed?: boolean;
  groq_fallback?: boolean;
  groq_attempt?: {
    raw_text_len: number;
    text_len: number;
    error?: string;
  };
  attempts?: Array<{
    model: string;
    raw_text_len: number;
    text_len: number;
    error?: string;
    dg_duration?: number;
    dg_channels?: number;
    language?: string;
  }>;
};

type TranscribeResult = {
  text: string;
  confidence: number | null;
  bytes: number;
  mime_type: string;
  elapsed_ms: number;
  no_speech?: boolean;
  error?: string;
  debug?: TranscribeDebug;
};

type LogEntry = {
  id: string;
  ts: string;
  stage: string;
  detail: Record<string, unknown>;
};

type TranscriptLine = {
  id: string;
  text: string;
  confidence: number | null;
  at: string;
};

function newId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function noSpeechMessage(debug?: TranscribeDebug, peak?: number): string {
  const vol = debug?.mean_volume_db;
  if (peak != null && peak < 0.01) {
    return "Mic level very low — check input device and speak closer to the microphone.";
  }
  if (vol != null && vol < -45) {
    return `Audio too quiet (${vol} dB) — speak louder or move closer to the mic.`;
  }
  if (debug?.groq_attempt?.text_len) {
    return "Groq returned text but it was filtered as junk — try speaking more clearly.";
  }
  if (debug?.groq_attempt?.error) {
    return `Deepgram heard nothing; Groq fallback failed: ${debug.groq_attempt.error}`;
  }
  const dgDur = debug?.attempts?.[0]?.dg_duration;
  if (dgDur != null && dgDur < 0.5) {
    return `Deepgram decoded only ${dgDur}s of audio — WAV format may be wrong. Hard-refresh and retry.`;
  }
  const attempts = debug?.attempts?.map((a) => `${a.model}:${a.raw_text_len}`).join(", ");
  return `No speech detected by Deepgram${attempts ? ` (${attempts})` : ""}. Speak clearly for the full 6 seconds.`;
}

export default function VoiceTranscriptPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState("");
  const [lines, setLines] = useState<TranscriptLine[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [recording, setRecording] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [micError, setMicError] = useState("");
  const [countdown, setCountdown] = useState(0);

  const cancelRef = useRef(false);
  const timerRef = useRef<number | null>(null);

  const pushLog = useCallback((stage: string, detail: Record<string, unknown>) => {
    setLogs((prev) => [
      { id: newId(), ts: new Date().toISOString(), stage, detail },
      ...prev,
    ].slice(0, 80));
  }, []);

  const loadHealth = useCallback(async () => {
    setHealthError("");
    try {
      const data = await api<Health>("/api/v1/doctor/transcript/health");
      setHealth(data);
      pushLog("health_ok", data as unknown as Record<string, unknown>);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Health check failed";
      setHealthError(message);
      pushLog("health_error", { error: message });
    }
  }, [pushLog]);

  useEffect(() => {
    void loadHealth();
  }, [loadHealth]);

  const clearTimers = () => {
    if (timerRef.current != null) window.clearInterval(timerRef.current);
    timerRef.current = null;
    setCountdown(0);
  };

  useEffect(() => () => {
    cancelRef.current = true;
    clearTimers();
  }, []);

  const transcribeBlob = useCallback(
    async (blob: Blob, peak?: number) => {
      const mime = blob.type.split(";")[0] || "audio/wav";
      pushLog("chunk_ready", { bytes: blob.size, mime_type: mime, peak_amplitude: peak });

      if (blob.size < MIN_BYTES) {
        pushLog("chunk_skipped", { reason: "too_small", bytes: blob.size });
        setMicError("Recording too short — try again and speak for the full 6 seconds.");
        return;
      }

      setUploading(true);
      const form = new FormData();
      const ext = mime.includes("wav") ? "wav" : "webm";
      form.append("file", new Blob([blob], { type: mime }), `recording.${ext}`);

      try {
        pushLog("transcribe_request", { bytes: blob.size, mime_type: mime });
        const data = await apiUpload<TranscribeResult>(
          "/api/v1/doctor/transcript/transcribe",
          form,
          true,
        );
        pushLog("transcribe_response", data as unknown as Record<string, unknown>);

        if (data.text) {
          setMicError("");
          setLines((prev) => [
            ...prev,
            {
              id: newId(),
              text: data.text,
              confidence: data.confidence,
              at: new Date().toLocaleTimeString(),
            },
          ]);
        } else if (data.error) {
          setMicError(data.error);
        } else if (data.no_speech) {
          setMicError(noSpeechMessage(data.debug, peak));
        }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Transcription failed";
        setMicError(message);
        pushLog("transcribe_error", { error: message });
      } finally {
        setUploading(false);
      }
    },
    [pushLog],
  );

  const startRecording = useCallback(async () => {
    if (recording || uploading) return;
    setMicError("");
    if (!health?.available) {
      setMicError(health?.error || "Deepgram is not configured on the server.");
      return;
    }

    cancelRef.current = false;
    setRecording(true);
    pushLog("recording_start", { duration_ms: RECORD_MS, format: "audio/wav" });

    const endAt = Date.now() + RECORD_MS;
    setCountdown(Math.ceil(RECORD_MS / 1000));
    timerRef.current = window.setInterval(() => {
      setCountdown(Math.max(0, Math.ceil((endAt - Date.now()) / 1000)));
    }, 200);

    try {
      const captured = await captureMicWav(RECORD_MS);
      clearTimers();
      setRecording(false);

      if (cancelRef.current) return;

      pushLog("recording_complete", {
        bytes: captured.blob.size,
        samples: captured.samples,
        peak_amplitude: captured.peak,
        sample_rate: captured.sampleRate,
        capture_sample_rate: captured.captureSampleRate,
      });

      await transcribeBlob(captured.blob, captured.peak);
    } catch (err: unknown) {
      clearTimers();
      setRecording(false);
      const message = err instanceof Error ? err.message : "Microphone access denied";
      setMicError(message);
      pushLog("mic_error", { error: message });
    }
  }, [health, pushLog, recording, transcribeBlob, uploading]);

  const cancelRecording = () => {
    cancelRef.current = true;
    clearTimers();
    setRecording(false);
    pushLog("recording_cancelled", {});
  };

  const clearAll = () => {
    setLines([]);
    setLogs([]);
    setMicError("");
  };

  return (
    <div className="voice-transcript-lab">
      <header className="voice-transcript-lab-head">
        <div>
          <h1>Voice → transcript test</h1>
          <p className="voice-transcript-lab-sub">
            Records 16 kHz WAV from your mic (not WebM), sends to Deepgram, and logs every step.
          </p>
        </div>
        <Link to="/doctor" className="dp-btn dp-btn--outline dp-btn--sm">
          Back to dashboard
        </Link>
      </header>

      <section className="voice-transcript-lab-cards">
        <article className="voice-transcript-lab-card">
          <h2>Server</h2>
          {healthError && <p className="aura-chat-error">{healthError}</p>}
          {health && (
            <ul className="voice-transcript-lab-meta">
              <li>Provider: {health.provider}</li>
              <li>Model: {health.model ?? "—"}</li>
              <li>Deepgram: {health.available ? "OK" : "missing key"}</li>
              <li>ffmpeg: {health.ffmpeg_available ? "OK" : "not found"}</li>
            </ul>
          )}
          <button type="button" className="dp-btn dp-btn--outline dp-btn--sm" onClick={() => void loadHealth()}>
            Refresh health
          </button>
        </article>

        <article className="voice-transcript-lab-card">
          <h2>Record</h2>
          <div className="voice-transcript-lab-actions">
            {!recording ? (
              <button
                type="button"
                className="dp-btn dp-btn--primary"
                disabled={uploading || !health?.available}
                onClick={() => void startRecording()}
              >
                {uploading ? "Transcribing…" : "Record 6 seconds"}
              </button>
            ) : (
              <button type="button" className="dp-btn dp-btn--outline" onClick={cancelRecording}>
                Cancel ({countdown}s)
              </button>
            )}
            <button type="button" className="dp-btn dp-btn--outline dp-btn--sm" onClick={clearAll}>
              Clear
            </button>
          </div>
          {recording && (
            <p className="voice-transcript-lab-status voice-transcript-lab-status--live">
              Recording… speak now ({countdown}s left)
            </p>
          )}
          {micError && <p className="aura-chat-error">{micError}</p>}
        </article>
      </section>

      <section className="voice-transcript-lab-panel">
        <h2>Transcript lines</h2>
        {lines.length === 0 ? (
          <p className="video-transcript-muted">Speak after pressing Record — lines appear here.</p>
        ) : (
          <ul className="voice-transcript-lab-lines">
            {lines.map((line) => (
              <li key={line.id}>
                <span className="voice-transcript-lab-line-time">{line.at}</span>
                <p>{line.text}</p>
                {line.confidence != null && (
                  <span className="voice-transcript-lab-line-conf">
                    confidence {(line.confidence * 100).toFixed(0)}%
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="voice-transcript-lab-panel">
        <h2>Event log</h2>
        {logs.length === 0 ? (
          <p className="video-transcript-muted">API and capture events will appear here.</p>
        ) : (
          <div className="voice-transcript-lab-log">
            {logs.map((entry) => (
              <details key={entry.id} className="voice-transcript-lab-log-item" open={entry.stage === "transcribe_response"}>
                <summary>
                  <code>{entry.ts.slice(11, 19)}</code> {entry.stage}
                </summary>
                <pre>{JSON.stringify(entry.detail, null, 2)}</pre>
              </details>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
