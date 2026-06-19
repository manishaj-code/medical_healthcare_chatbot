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

export function useConsultationTranscript(appointmentId: string | undefined, enabled: boolean) {
  const [session, setSession] = useState<TranscriptSession | null>(null);
  const [sttConfig, setSttConfig] = useState<TranscriptSttConfig | null>(null);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [loading, setLoading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");
  const [captureError, setCaptureError] = useState("");
  const [listening, setListening] = useState(false);
  const lastSegmentIdRef = useRef<string | null>(null);
  const startedRef = useRef(false);

  const refresh = useCallback(async () => {
    if (!appointmentId || !enabled) return;
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
      setWarning("");
      try {
        const qs = roomId ? `?room_id=${encodeURIComponent(roomId)}` : "";
        const data = await api<TranscriptStartResponse>(
          `/api/v1/doctor/appointments/${appointmentId}/transcript/start${qs}`,
          { method: "POST" },
        );
        setSession(data.session);
        setSttConfig(data.stt);
        if (data.stt?.error) {
          setError(data.stt.error);
        } else if (data.stt?.warning) {
          setWarning(data.stt.warning);
        }
        startedRef.current = true;
        lastSegmentIdRef.current = null;
        setSegments([]);
        setCaptureError("");
        await refresh();
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Could not start transcript");
      } finally {
        setLoading(false);
      }
    },
    [appointmentId, enabled, refresh],
  );

  const stop = useCallback(async () => {
    if (!appointmentId || !startedRef.current) return;
    try {
      await api(`/api/v1/doctor/appointments/${appointmentId}/transcript/stop`, { method: "POST" });
    } catch {
      // ignore
    } finally {
      startedRef.current = false;
    }
  }, [appointmentId]);

  const uploadChunk = useCallback(
    async (blob: Blob, speakerRole = "unknown", speakerLabel = "Discussion") => {
      if (!appointmentId || !enabled || !startedRef.current) return;
      setListening(true);
      const form = new FormData();
      const ext = blob.type.includes("webm") ? "webm" : "ogg";
      form.append("file", blob, `chunk.${ext}`);
      form.append("speaker_role", speakerRole);
      form.append("speaker_label", speakerLabel);
      try {
        const data = await apiUpload<{
          segment: TranscriptSegment | null;
          skipped?: boolean;
          reason?: string;
        }>(
          `/api/v1/doctor/appointments/${appointmentId}/transcript/chunk`,
          form,
        );
        if (data.segment) {
          setCaptureError("");
          setSegments((prev) => {
            if (prev.some((s) => s.id === data.segment!.id)) return prev;
            return [...prev, data.segment!];
          });
          lastSegmentIdRef.current = data.segment.id;
        } else if (data.reason === "no_speech") {
          setCaptureError("");
        }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Transcript upload failed";
        setCaptureError(message);
      } finally {
        setListening(false);
      }
    },
    [appointmentId, enabled],
  );

  const postSegment = useCallback(
    async (
      text: string,
      speakerRole = "unknown",
      speakerLabel = "Discussion",
      confidence?: number,
    ) => {
      if (!appointmentId || !enabled || !startedRef.current || !text.trim()) return;
      try {
        const data = await api<{ segment: TranscriptSegment | null; skipped?: boolean }>(
          `/api/v1/doctor/appointments/${appointmentId}/transcript/segment`,
          {
            method: "POST",
            body: JSON.stringify({
              text,
              speaker_role: speakerRole,
              speaker_label: speakerLabel,
              is_final: true,
              confidence: confidence ?? null,
            }),
          },
        );
        if (data.segment) {
          setSegments((prev) => {
            if (prev.some((s) => s.id === data.segment!.id)) return prev;
            return [...prev, data.segment!];
          });
          lastSegmentIdRef.current = data.segment.id;
        }
      } catch {
        // keep call running
      }
    },
    [appointmentId, enabled],
  );

  const analyze = useCallback(async () => {
    if (!appointmentId) return null;
    setAnalyzing(true);
    setError("");
    try {
      const data = await api<TranscriptAiSuggestions>(
        `/api/v1/doctor/appointments/${appointmentId}/consultation/ai-from-transcript`,
        { method: "POST" },
      );
      await refresh();
      return data;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Analysis failed");
      return null;
    } finally {
      setAnalyzing(false);
    }
  }, [appointmentId, refresh]);

  useEffect(() => {
    if (!enabled || !appointmentId) return undefined;
    const id = window.setInterval(() => void refresh(), 2500);
    return () => window.clearInterval(id);
  }, [enabled, appointmentId, refresh]);

  useEffect(() => {
    return () => {
      void stop();
    };
  }, [stop]);

  return {
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
    stop,
    refresh,
    uploadChunk,
    postSegment,
    analyze,
    isActive: startedRef.current,
    sessionReady: session?.status === "active",
  };
}
