import type { TranscriptAiSuggestions } from "../../types/consultationTranscript";
import TranscriptSummaryCard from "./TranscriptSummaryCard";

interface Props {
  suggestions: TranscriptAiSuggestions | null;
  analyzing: boolean;
  error?: string;
  segmentCount: number;
  sessionActive: boolean;
  lastAnalyzedAt?: string | null;
  onApplyToForm?: () => void;
  applyLabel?: string;
  onAnalyzeNow?: () => void;
  compact?: boolean;
  hideHeader?: boolean;
}

function formatAnalyzedWhen(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export default function InVisitSummaryPanel({
  suggestions,
  analyzing,
  error,
  segmentCount,
  sessionActive,
  lastAnalyzedAt,
  onApplyToForm,
  applyLabel,
  onAnalyzeNow,
  compact,
  hideHeader = false,
}: Props) {
  const analyzedLabel = formatAnalyzedWhen(lastAnalyzedAt);

  return (
    <div className={`dp-in-visit-summary${compact ? " dp-in-visit-summary--compact" : ""}`}>
      {!hideHeader && (
        <header className="dp-in-visit-summary-head">
          <div className="dp-consult-section-head" style={{ marginBottom: 0 }}>
            <span className="material-symbols-outlined filled-icon">record_voice_over</span>
            <div>
              <h2>In-visit summary</h2>
              <p>
                {sessionActive
                  ? "Updates automatically from the live video transcript."
                  : "Built from the consultation transcript."}
                {analyzedLabel ? ` Last updated ${analyzedLabel}.` : ""}
              </p>
            </div>
          </div>
          <div className="dp-in-visit-summary-actions">
            {analyzing && (
              <span className="dp-in-visit-summary-status">
                <span className="dp-spinner dp-spinner--sm" aria-hidden />
                Analyzing…
              </span>
            )}
            {onAnalyzeNow && (
              <button
                type="button"
                className="dp-btn dp-btn--sm dp-btn--outline"
                disabled={analyzing || segmentCount < 2}
                onClick={() => void onAnalyzeNow()}
              >
                Refresh
              </button>
            )}
          </div>
        </header>
      )}

      {error && (
        <p className="dp-consult-prep-transcript-analyze-error" role="alert">
          {error}
        </p>
      )}

      {suggestions ? (
        <TranscriptSummaryCard
          suggestions={suggestions}
          onApplyToForm={onApplyToForm}
          applyLabel={applyLabel}
          applyDisabled={analyzing}
        />
      ) : (
        <div className="dp-in-visit-summary-empty">
          {segmentCount > 0 ? (
            <>
              <span className="material-symbols-outlined">hourglass_top</span>
              <p>
                {analyzing
                  ? "Generating in-visit summary from the discussion…"
                  : "Waiting for enough transcript content — summary will appear shortly."}
              </p>
            </>
          ) : (
            <>
              <span className="material-symbols-outlined">subtitles</span>
              <p>
                Join the video call to capture a live transcript. This panel will fill in
                automatically as you and the patient talk.
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
