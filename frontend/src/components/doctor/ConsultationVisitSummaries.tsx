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

function formatAnalyzedWhen(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

function VisitSummaryColumnHead({
  icon,
  title,
  subtitle,
  actions,
}: {
  icon: string;
  title: string;
  subtitle: string;
  actions?: ReactNode;
}) {
  return (
    <header className="dp-consult-visit-column-head">
      <div className="dp-consult-section-head dp-consult-section-head--flush">
        <span className="material-symbols-outlined filled-icon">{icon}</span>
        <div>
          <h2>{title}</h2>
          <p>{subtitle}</p>
        </div>
      </div>
      {actions}
    </header>
  );
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

  const isActive = layout === "active";
  const analyzedLabel = formatAnalyzedWhen(lastAnalyzedAt);
  const inVisitSubtitle = sessionActive
    ? "Updates automatically from the live video transcript."
    : "Built from the consultation transcript.";
  const inVisitDetail = analyzedLabel ? ` Last updated ${analyzedLabel}.` : "";

  const inVisitActions = (
    <div className="dp-in-visit-summary-actions">
      {analyzing && (
        <span className="dp-in-visit-summary-status">
          <span className="dp-spinner dp-spinner--sm" aria-hidden />
          Analyzing…
        </span>
      )}
      <button
        type="button"
        className="dp-btn dp-btn--sm dp-btn--outline"
        disabled={analyzing || segmentCount < 2}
        onClick={() => void analyzeNow()}
      >
        Refresh
      </button>
    </div>
  );

  return (
    <section
      className={`dp-consult-visit-summaries dp-consult-visit-summaries--${layout}`}
      aria-label="Visit summaries"
    >
      <article className="dp-consult-visit-summary dp-consult-visit-summary--pre">
        {isActive && (
          <VisitSummaryColumnHead
            icon="auto_awesome"
            title="Pre-visit summary"
            subtitle="From patient triage and intake"
          />
        )}
        <div className="dp-consult-visit-summary-body">{preVisit}</div>
      </article>
      <article className="dp-consult-visit-summary dp-consult-visit-summary--in">
        {isActive && (
          <VisitSummaryColumnHead
            icon="record_voice_over"
            title="In-visit summary"
            subtitle={`${inVisitSubtitle}${inVisitDetail}`}
            actions={inVisitActions}
          />
        )}
        <div className="dp-consult-visit-summary-body">
          <InVisitSummaryPanel
            suggestions={suggestions}
            analyzing={analyzing}
            error={error}
            segmentCount={segmentCount}
            sessionActive={sessionActive}
            lastAnalyzedAt={lastAnalyzedAt}
            compact={isActive}
            hideHeader={isActive}
            onAnalyzeNow={isActive ? undefined : analyzeNow}
            applyLabel={applyLabel}
            onApplyToForm={
              suggestions && onApplyTranscriptToForm
                ? () => onApplyTranscriptToForm(suggestions)
                : undefined
            }
          />
        </div>
      </article>
    </section>
  );
}
