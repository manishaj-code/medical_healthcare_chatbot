interface Props {
  aptId: string;
  preview?: string | null;
  summary?: string | null;
  segmentCount?: number;
  hasTranscript?: boolean;
  compact?: boolean;
}

function SkeletonLines() {
  return (
    <div className="dp-visit-transcript-skeleton-lines" aria-hidden>
      <span />
      <span />
      <span className="dp-visit-transcript-skeleton-lines--short" />
    </div>
  );
}

export default function VisitTranscriptExcerpt({
  aptId,
  preview,
  summary,
  segmentCount,
  hasTranscript,
  compact,
}: Props) {
  const hasContent = Boolean(hasTranscript || preview?.trim() || summary?.trim());

  return (
    <section
      className={`dp-visit-block dp-visit-block--transcript${compact ? " dp-visit-block--transcript-compact" : ""}`}
      aria-label={`Video transcript ${aptId}`}
    >
      <div className="dp-visit-block-head">
        <span className="material-symbols-outlined">subtitles</span>
        <h4>Video transcript</h4>
        {!hasContent && <span className="dp-tag dp-tag--neutral">No transcript</span>}
      </div>

      {hasContent ? (
        <>
          {summary && <p className="dp-visit-transcript-summary">{summary}</p>}
          {preview && <blockquote className="dp-visit-transcript-preview">{preview}</blockquote>}
          {segmentCount != null && segmentCount > 0 && (
            <p className="dp-muted-note">{segmentCount} segments captured</p>
          )}
        </>
      ) : (
        <div className="dp-visit-transcript-placeholder">
          <p className="dp-muted-note">
            No transcript was captured for this video visit.
          </p>
          <SkeletonLines />
        </div>
      )}
    </section>
  );
}
