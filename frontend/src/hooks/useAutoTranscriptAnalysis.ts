import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { TranscriptAiSuggestions, TranscriptSnapshot } from "../types/consultationTranscript";
import { insightsToSuggestions } from "../utils/transcriptInsights";

const POLL_MS = 5_000;
const ANALYZE_DEBOUNCE_MS = 20_000;
const MIN_SEGMENTS = 2;
const SEGMENTS_DELTA_REANALYZE = 3;

interface Options {
  appointmentId: string | undefined;
  enabled: boolean;
  onAnalyzeComplete?: (data: TranscriptAiSuggestions) => void;
}

export function useAutoTranscriptAnalysis({
  appointmentId,
  enabled,
  onAnalyzeComplete,
}: Options) {
  const [suggestions, setSuggestions] = useState<TranscriptAiSuggestions | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState("");
  const [segmentCount, setSegmentCount] = useState(0);
  const [sessionActive, setSessionActive] = useState(false);
  const [lastAnalyzedAt, setLastAnalyzedAt] = useState<string | null>(null);

  const analyzedSegmentCountRef = useRef(0);
  const segmentCountRef = useRef(0);
  const analyzingRef = useRef(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onCompleteRef = useRef(onAnalyzeComplete);
  onCompleteRef.current = onAnalyzeComplete;

  const refreshSnapshot = useCallback(async () => {
    if (!appointmentId || !enabled) return null;
    try {
      const data = await api<TranscriptSnapshot>(
        `/api/v1/doctor/appointments/${appointmentId}/transcript`,
      );
      const count = data.segments.length;
      segmentCountRef.current = count;
      setSegmentCount(count);
      setSessionActive(data.session?.status === "active");
      setError("");

      const stored = insightsToSuggestions(data.session?.last_insights ?? null);
      if (stored) {
        setSuggestions((prev) => prev ?? stored);
        if (data.session?.last_insights?.analyzed_at) {
          setLastAnalyzedAt(String(data.session.last_insights.analyzed_at));
        }
        const storedCount = Number(data.session?.last_insights?.segment_count ?? 0);
        if (storedCount > analyzedSegmentCountRef.current) {
          analyzedSegmentCountRef.current = storedCount;
        }
      }
      return data;
    } catch {
      return null;
    }
  }, [appointmentId, enabled]);

  const runAnalyze = useCallback(async () => {
    if (!appointmentId || analyzingRef.current) return;
    analyzingRef.current = true;
    setAnalyzing(true);
    setError("");
    try {
      const data = await api<TranscriptAiSuggestions>(
        `/api/v1/doctor/appointments/${appointmentId}/consultation/ai-from-transcript`,
        { method: "POST" },
      );
      setSuggestions(data);
      setLastAnalyzedAt(new Date().toISOString());
      analyzedSegmentCountRef.current = segmentCountRef.current;
      onCompleteRef.current?.(data);
      await refreshSnapshot();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Transcript analysis failed");
    } finally {
      analyzingRef.current = false;
      setAnalyzing(false);
    }
  }, [appointmentId, refreshSnapshot]);

  const scheduleAnalyze = useCallback(
    (count: number) => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
      debounceRef.current = window.setTimeout(() => {
        debounceRef.current = null;
        if (count < MIN_SEGMENTS) return;
        if (
          analyzedSegmentCountRef.current > 0 &&
          count - analyzedSegmentCountRef.current < SEGMENTS_DELTA_REANALYZE
        ) {
          return;
        }
        void runAnalyze();
      }, ANALYZE_DEBOUNCE_MS);
    },
    [runAnalyze],
  );

  useEffect(() => {
    if (!enabled || !appointmentId) return undefined;
    void refreshSnapshot();
    const id = window.setInterval(() => void refreshSnapshot(), POLL_MS);
    return () => window.clearInterval(id);
  }, [enabled, appointmentId, refreshSnapshot]);

  useEffect(() => {
    if (!enabled || !appointmentId || segmentCount < MIN_SEGMENTS) return;
    scheduleAnalyze(segmentCount);
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, [enabled, appointmentId, segmentCount, scheduleAnalyze]);

  useEffect(() => {
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current);
    };
  }, []);

  return {
    suggestions,
    analyzing,
    error,
    segmentCount,
    sessionActive,
    lastAnalyzedAt,
    refresh: refreshSnapshot,
    analyzeNow: runAnalyze,
  };
}
