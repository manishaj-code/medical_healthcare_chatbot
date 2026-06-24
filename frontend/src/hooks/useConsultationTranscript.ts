import { useCallback, useEffect, useRef, useState } from "react";
import { api, apiUpload } from "../api/client";
import type {
  TranscriptAiSuggestions,
  TranscriptSegment,
  TranscriptSession,
  TranscriptSnapshot,
  TranscriptStartResponse,
  TranscriptSttConfig,
} from "../types/consultationTranscript";
import { mapTranscriptAnalyzeError, mapTranscriptUploadError } from "../utils/transcriptErrors";

const MAX_CONCURRENT_UPLOADS = 2;
const MAX_UPLOAD_RETRIES = 1;

type ChunkJob = {
  blob: Blob;
  speakerRole: string;
  speakerLabel: string;
  attempt: number;
};

export function useConsultationTranscript(appointmentId: string | undefined, enabled: boolean) {
  const [session, setSession] = useState<TranscriptSession | null>(null);
  const [sttConfig, setSttConfig] = useState<TranscriptSttConfig | null>(null);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [captureError, setCaptureError] = useState("");
  const [listening, setListening] = useState(false);
  const [pendingUploads, setPendingUploads] = useState(0);
  const [chunksSent, setChunksSent] = useState(0);
  const [lastChunkStatus, setLastChunkStatus] = useState("");
  const lastSegmentIdRef = useRef<string | null>(null);
  const startedRef = useRef(false);
  const stoppingRef = useRef(false);
  const sessionRef = useRef<TranscriptSession | null>(null);
  const queueRef = useRef<ChunkJob[]>([]);
  const activeUploadsRef = useRef(0);
  const drainUploadQueueRef = useRef<() => void>(() => undefined);

  sessionRef.current = session;

  const syncUploadStats = useCallback(() => {
    setPendingUploads(queueRef.current.length + activeUploadsRef.current);
    setListening(activeUploadsRef.current > 0 || queueRef.current.length > 0);
  }, []);

  const refresh = useCallback(async () => {
    if (!appointmentId || !enabled || !startedRef.current) return;
    try {
      const since = lastSegmentIdRef.current;
      const path = since
        ? `/api/v1/doctor/appointments/${appointmentId}/transcript?since_id=${since}`
        : `/api/v1/doctor/appointments/${appointmentId}/transcript`;
      const data = await api<TranscriptSnapshot>(path);
      if (data.session) setSession(data.session);
      if (data.segments.length > 0) {
        setSegments((prev) => {
          const ids = new Set(prev.map((s) => s.id));
          const merged = [...prev];
          for (const seg of data.segments) {
            if (!ids.has(seg.id)) merged.push(seg);
          }
          return merged;
        });
        lastSegmentIdRef.current = data.segments[data.segments.length - 1]?.id ?? lastSegmentIdRef.current;
      }
    } catch {
      // ignore polling errors
    }
  }, [appointmentId, enabled]);

  const start = useCallback(
    async (roomId?: string) => {
      if (!appointmentId || !enabled || startedRef.current) return;
      setLoading(true);
      setError("");
      try {
        const qs = roomId ? `?room_id=${encodeURIComponent(roomId)}` : "";
        const data = await api<TranscriptStartResponse>(
          `/api/v1/doctor/appointments/${appointmentId}/transcript/start${qs}`,
          { method: "POST" },
        );
        setSession(data.session);
        setSttConfig(data.stt);
        if (data.stt?.error) setError(data.stt.error);
        startedRef.current = true;
        lastSegmentIdRef.current = null;
        setSegments([]);
        setCaptureError("");
        queueRef.current = [];
        activeUploadsRef.current = 0;
        syncUploadStats();
        await refresh();
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Could not start transcript");
      } finally {
        setLoading(false);
      }
    },
    [appointmentId, enabled, refresh, syncUploadStats],
  );

  const stop = useCallback(async () => {
    if (!appointmentId || stoppingRef.current) return;
    const sessionActive =
      startedRef.current || sessionRef.current?.status === "active";
    if (!sessionActive) return;

    stoppingRef.current = true;
    startedRef.current = false;
    queueRef.current = [];
    activeUploadsRef.current = 0;
    syncUploadStats();
    setSession((prev) => (prev ? { ...prev, status: "completed" } : null));

    try {
      const data = await api<{ session: TranscriptSession | null; stopped?: boolean }>(
        `/api/v1/doctor/appointments/${appointmentId}/transcript/stop`,
        { method: "POST" },
      );
      if (data.session) setSession(data.session);
    } catch {
      // ignore — session may already be completed
    } finally {
      stoppingRef.current = false;
      syncUploadStats();
    }
  }, [appointmentId, syncUploadStats]);

  const sendChunkUpload = useCallback(
    async (
      blob: Blob,
      speakerRole: string,
      speakerLabel: string,
    ): Promise<{ ok: boolean; reason?: string }> => {
      if (!appointmentId || !enabled) return { ok: false, reason: "inactive" };

      const form = new FormData();
      const mime = blob.type.split(";")[0] || "audio/wav";
      const ext = mime.includes("wav") ? "wav" : "webm";
      form.append("file", new Blob([blob], { type: mime }), `chunk.${ext}`);
      form.append("speaker_role", speakerRole);
      form.append("speaker_label", speakerLabel);

      try {
        const data = await apiUpload<{
          segment: TranscriptSegment | null;
          skipped?: boolean;
          reason?: string;
          detail?: string;
        }>(`/api/v1/doctor/appointments/${appointmentId}/transcript/chunk`, form, true);

        if (data.segment) {
          setCaptureError("");
          setSegments((prev) => {
            if (prev.some((s) => s.id === data.segment!.id)) return prev;
            return [...prev, data.segment!];
          });
          lastSegmentIdRef.current = data.segment.id;
        }

        if (
          data.reason === "no_speech" ||
          data.reason === "too_small" ||
          data.reason === "duplicate" ||
          data.reason === "session_ended"
        ) {
          setLastChunkStatus(
            data.reason === "no_speech"
              ? "Last chunk: no speech detected — speak louder and keep mic unmuted"
              : data.reason === "too_small"
                ? "Last chunk: audio too short"
                : data.reason === "session_ended"
                  ? "Last chunk: transcript session ended"
                  : "Last chunk: duplicate line skipped",
          );
          return { ok: true, reason: data.reason };
        }

        if (data.reason === "stt_error") {
          const detail =
            data.detail || "Speech recognition failed on the server. Check Deepgram API key and logs.";
          setLastChunkStatus(`Last chunk failed: ${detail}`);
          return { ok: false, reason: detail };
        }

        setChunksSent((n) => n + 1);
        if (data.segment) {
          setLastChunkStatus(`Last chunk: line added (${data.segment.text.slice(0, 48)}…)`);
        }
        return { ok: true };
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Transcript upload failed";
        setLastChunkStatus(`Last chunk failed: ${message}`);
        return { ok: false, reason: message };
      }
    },
    [appointmentId, enabled],
  );

  drainUploadQueueRef.current = () => {
    while (activeUploadsRef.current < MAX_CONCURRENT_UPLOADS && queueRef.current.length > 0) {
      const job = queueRef.current.shift();
      if (!job) break;

      activeUploadsRef.current += 1;
      syncUploadStats();

      void (async () => {
        try {
          const result = await sendChunkUpload(job.blob, job.speakerRole, job.speakerLabel);
          if (!result.ok && job.attempt < MAX_UPLOAD_RETRIES) {
            queueRef.current.push({ ...job, attempt: job.attempt + 1 });
          } else if (!result.ok) {
            setCaptureError(mapTranscriptUploadError(result.reason || "Transcript upload failed"));
          }
        } finally {
          activeUploadsRef.current = Math.max(0, activeUploadsRef.current - 1);
          syncUploadStats();
          drainUploadQueueRef.current();
        }
      })();
    }
  };

  const uploadChunk = useCallback(
    (blob: Blob, speakerRole = "unknown", speakerLabel = "Discussion") => {
      if (
        !appointmentId ||
        !enabled ||
        !startedRef.current ||
        sessionRef.current?.status !== "active"
      ) {
        return;
      }
      queueRef.current.push({ blob, speakerRole, speakerLabel, attempt: 0 });
      syncUploadStats();
      drainUploadQueueRef.current();
    },
    [appointmentId, enabled, syncUploadStats],
  );

  const analyze = useCallback(async () => {
    if (!appointmentId) return null;
    if (segments.length === 0) {
      setError(mapTranscriptAnalyzeError("No transcript available for this consultation."));
      return null;
    }

    setAnalyzing(true);
    setError("");
    try {
      await refresh();
      const data = await api<TranscriptAiSuggestions>(
        `/api/v1/doctor/appointments/${appointmentId}/consultation/ai-from-transcript`,
        { method: "POST" },
      );
      await refresh();
      return data;
    } catch (err: unknown) {
      setError(mapTranscriptAnalyzeError(err instanceof Error ? err.message : "Analysis failed"));
      return null;
    } finally {
      setAnalyzing(false);
    }
  }, [appointmentId, refresh, segments.length]);

  useEffect(() => {
    if (!enabled || !appointmentId || !startedRef.current || session?.status !== "active") {
      return undefined;
    }
    const id = window.setInterval(() => void refresh(), 2500);
    return () => window.clearInterval(id);
  }, [enabled, appointmentId, session?.status, refresh]);

  useEffect(() => {
    return () => {
      queueRef.current = [];
      activeUploadsRef.current = 0;
      if (!appointmentId || stoppingRef.current) return;
      const sessionActive =
        startedRef.current || sessionRef.current?.status === "active";
      if (!sessionActive) return;
      startedRef.current = false;
      void api(
        `/api/v1/doctor/appointments/${appointmentId}/transcript/stop`,
        { method: "POST" },
      ).catch(() => undefined);
    };
  }, [appointmentId]);

  return {
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
    refresh,
    uploadChunk,
    analyze,
    sessionReady: session?.status === "active",
  };
}