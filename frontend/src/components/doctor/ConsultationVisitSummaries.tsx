import type { ReactNode } from "react";
import type { TranscriptAiSuggestions } from "../../types/consultationTranscript";
import { useAutoTranscriptAnalysis } from "../../hooks/useAutoTranscriptAnalysis";
import InVisitSummaryPanel from "./InVisitSummaryPanel";

interface Props {
  appointmentId: string;
  preVisit: ReactNode;
  autoAnalyzeEnabled?: boolean;
  onTranscriptAnalyze?: (suggestions: TranscriptAiSuggestions) => void;
  onApplyTranscriptToForm?: (suggestions: TranscriptAiSuggestions) => void;
  applyLabel?: string;
  layout?: "prep" | "active";
}

export default function ConsultationVisitSummaries({
  appointmentId,
  preVisit,
  autoAnalyzeEnabled = true,
  onTranscriptAnalyze,
  onApplyTranscriptToForm,
  applyLabel = "Apply to consultation form",
  layout = "prep",
}: Props) {
  const {
    suggestions,
    analyzing,
    error,
    segmentCount,
    sessionActive,
    lastAnalyzedAt,
    analyzeNow,
  } = useAutoTranscriptAnalysis({
    appointmentId,
    enabled: autoAnalyzeEnabled,
    onAnalyzeComplete: onTranscriptAnalyze,
  });

  return (
    <section
      className={`dp-consult-visit-summaries dp-consult-visit-summaries--${layout}`}
      aria-label="Visit summaries"
    >
      <article className="dp-consult-visit-summary dp-consult-visit-summary--pre">
        {layout === "active" && (
          <p className="dp-consult-visit-summary-label">Pre-visit summary</p>
        )}
        {preVisit}
      </article>
      <article className="dp-consult-visit-summary dp-consult-visit-summary--in">
        <InVisitSummaryPanel
          suggestions={suggestions}
          analyzing={analyzing}
          error={error}
          segmentCount={segmentCount}
          sessionActive={sessionActive}
          lastAnalyzedAt={lastAnalyzedAt}
          compact={layout === "active"}
          onAnalyzeNow={analyzeNow}
          applyLabel={applyLabel}
          onApplyToForm={
            suggestions && onApplyTranscriptToForm
              ? () => onApplyTranscriptToForm(suggestions)
              : undefined
          }
        />
      </article>
    </section>
  );
}
