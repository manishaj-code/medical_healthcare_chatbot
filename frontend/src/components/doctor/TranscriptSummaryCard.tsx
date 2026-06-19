import type { TranscriptAiSuggestions } from "../../types/consultationTranscript";

interface Props {
  suggestions: TranscriptAiSuggestions;
  onApplyToForm?: () => void;
  applyDisabled?: boolean;
  applyLabel?: string;
}

function hasStructuredContent(data: TranscriptAiSuggestions): boolean {
  return Boolean(
    data.transcript_summary ||
      data.chief_complaint_suggestion ||
      (data.patient_concerns?.length ?? 0) > 0 ||
      data.differential_considerations.length > 0 ||
      data.suggested_investigations.length > 0 ||
      data.clinical_notes_draft ||
      data.suggested_medications.length > 0,
  );
}

export default function TranscriptSummaryCard({
  suggestions,
  onApplyToForm,
  applyDisabled,
  applyLabel = "Apply to consultation form",
}: Props) {
  if (!hasStructuredContent(suggestions)) {
    return (
      <div className="dp-transcript-summary-card dp-transcript-summary-card--empty">
        <p className="dp-muted-note" style={{ margin: 0 }}>
          Analysis completed but no structured suggestions were returned. Try again after more
          transcript content is captured.
        </p>
      </div>
    );
  }

  const investigations =
    suggestions.matched_catalog_tests?.length
      ? suggestions.matched_catalog_tests.map((t) => t.test_name)
      : suggestions.suggested_investigations;

  return (
    <section className="dp-transcript-summary-card" aria-label="Transcript AI summary">
      <header className="dp-transcript-summary-head">
        <div>
          <p className="dp-transcript-summary-eyebrow">
            <span className="material-symbols-outlined filled-icon">auto_awesome</span>
            Transcript AI summary
          </p>
          <h3>Clinical analysis from video discussion</h3>
        </div>
        {onApplyToForm && (
          <button
            type="button"
            className="dp-btn dp-btn--sm dp-btn--primary"
            disabled={applyDisabled}
            onClick={onApplyToForm}
          >
            <span className="material-symbols-outlined">edit_note</span>
            {applyLabel}
          </button>
        )}
      </header>

      {suggestions.chief_complaint_suggestion && (
        <div className="dp-transcript-summary-block">
          <h4>Suggested chief complaint</h4>
          <p>{suggestions.chief_complaint_suggestion}</p>
        </div>
      )}

      {suggestions.transcript_summary && (
        <div className="dp-transcript-summary-block dp-transcript-summary-block--highlight">
          <h4>Discussion summary</h4>
          <p>{suggestions.transcript_summary}</p>
        </div>
      )}

      {(suggestions.patient_concerns?.length ?? 0) > 0 && (
        <div className="dp-transcript-summary-block">
          <h4>Patient concerns</h4>
          <div className="dp-transcript-summary-tags">
            {suggestions.patient_concerns!.map((item) => (
              <span key={item} className="dp-tag dp-tag--info">
                {item}
              </span>
            ))}
          </div>
        </div>
      )}

      {suggestions.differential_considerations.length > 0 && (
        <div className="dp-transcript-summary-block">
          <h4>Differential considerations</h4>
          <ul className="dp-transcript-summary-list">
            {suggestions.differential_considerations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {investigations.length > 0 && (
        <div className="dp-transcript-summary-block">
          <h4>Suggested investigations</h4>
          <div className="dp-transcript-summary-tags">
            {investigations.map((item) => (
              <span key={item} className="dp-tag dp-tag--neutral">
                {item}
              </span>
            ))}
          </div>
        </div>
      )}

      {suggestions.suggested_follow_up_days != null && (
        <div className="dp-transcript-summary-block dp-transcript-summary-block--inline">
          <h4>Follow-up</h4>
          <p>Recommend follow-up in {suggestions.suggested_follow_up_days} day(s)</p>
        </div>
      )}

      {suggestions.clinical_notes_draft && (
        <div className="dp-transcript-summary-block">
          <h4>Clinical notes draft</h4>
          <pre className="dp-transcript-summary-notes">{suggestions.clinical_notes_draft}</pre>
        </div>
      )}

      {suggestions.suggested_medications.length > 0 && (
        <div className="dp-transcript-summary-block">
          <h4>Suggested medications</h4>
          <ul className="dp-transcript-summary-med-list">
            {suggestions.suggested_medications.map((med) => (
              <li key={med.medicine_name}>
                <strong>{med.medicine_name}</strong>
                {[med.strength, med.frequency, med.duration].filter(Boolean).join(" · ")}
                {med.rationale && <span className="dp-muted-note"> — {med.rationale}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {suggestions.allergy_warnings.length > 0 && (
        <div className="dp-transcript-summary-warnings">
          {suggestions.allergy_warnings.map((warning) => (
            <p key={warning}>
              <span className="material-symbols-outlined">warning</span>
              {warning}
            </p>
          ))}
        </div>
      )}

      <p className="dp-transcript-summary-disclaimer">{suggestions.disclaimer}</p>
    </section>
  );
}
