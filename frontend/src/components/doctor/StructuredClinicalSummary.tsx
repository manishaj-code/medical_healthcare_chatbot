import {
  type ClinicalSummaryFields,
  DEFAULT_CLINICAL_RECOMMENDATION,
  buildClinicalShortDescription,
  formatRiskLevelLabel,
  isEmptyClinicalValue,
  riskLevelCssVariant,
} from "../../utils/clinicalSummaryFormat";

type SummaryVariant = "full" | "compact" | "list";

interface Props {
  fields: ClinicalSummaryFields;
  variant?: SummaryVariant;
}

function MetricCard({
  label,
  value,
  emptyLabel,
  variant,
}: {
  label: string;
  value: string | null;
  emptyLabel: string;
  variant?: string;
}) {
  const empty = isEmptyClinicalValue(value);
  return (
    <div className={`dp-clinical-metric${empty ? " dp-clinical-metric--empty" : ""}`}>
      <span className="dp-clinical-metric-label">{label}</span>
      {empty ? (
        <span className="dp-clinical-metric-empty">{emptyLabel}</span>
      ) : variant ? (
        <span className={`dp-clinical-risk-badge dp-clinical-risk-badge--${variant}`}>{value}</span>
      ) : (
        <span className="dp-clinical-metric-value">{value}</span>
      )}
    </div>
  );
}

function ContextCard({
  label,
  icon,
  items,
  emptyLabel = "None recorded",
}: {
  label: string;
  icon: string;
  items: string[];
  emptyLabel?: string;
}) {
  const empty = items.length === 0;
  return (
    <div className={`dp-clinical-context-card${empty ? " dp-clinical-context-card--empty" : ""}`}>
      <div className="dp-clinical-context-head">
        <span className="material-symbols-outlined">{icon}</span>
        <span>{label}</span>
      </div>
      {empty ? (
        <p className="dp-clinical-context-empty">{emptyLabel}</p>
      ) : (
        <ul className="dp-clinical-context-list">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function StructuredClinicalSummary({ fields, variant = "full" }: Props) {
  const symptoms =
    fields.symptomLabels.length > 0
      ? fields.symptomLabels
      : [];
  const riskClass = riskLevelCssVariant(fields.riskLevel);
  const riskDisplay = formatRiskLevelLabel(fields.riskLevel);
  const recommendation =
    fields.recommendation && !isEmptyClinicalValue(fields.recommendation)
      ? fields.recommendation
      : DEFAULT_CLINICAL_RECOMMENDATION;
  const shortDescription = buildClinicalShortDescription(fields);

  return (
    <div className={`dp-clinical-summary dp-clinical-summary--${variant}`}>
      <section className="dp-clinical-hero">
        <p className="dp-clinical-hero-label">Chief Complaint</p>
        {symptoms.length > 0 ? (
          <div className="dp-clinical-symptom-chips">
            {symptoms.map((s) => (
              <span key={s} className="dp-clinical-symptom-chip">
                {s}
              </span>
            ))}
          </div>
        ) : (
          <p className="dp-clinical-hero-empty">No symptoms recorded yet</p>
        )}
      </section>

      <section className="dp-clinical-metrics" aria-label="Assessment overview">
        <MetricCard label="Duration" value={fields.duration} emptyLabel="Not recorded" />
        <MetricCard
          label="Risk Level"
          value={riskDisplay}
          emptyLabel="Not assessed"
          variant={riskDisplay ? riskClass : undefined}
        />
        <MetricCard
          label="Specialty"
          value={fields.recommendedSpecialty}
          emptyLabel="Not specified"
        />
      </section>

      <section className="dp-clinical-context-grid" aria-label="Clinical context">
        <ContextCard label="Medical History" icon="history" items={fields.medicalHistory} />
        <ContextCard label="Medications" icon="medication" items={fields.medications} />
        <ContextCard label="Allergies" icon="warning" items={fields.allergies} emptyLabel="No known allergies" />
      </section>

      {shortDescription && shortDescription.length > 0 && (
        <section className="dp-clinical-short-desc" aria-label="Short description">
          <div className="dp-clinical-short-desc-head">
            <span className="material-symbols-outlined filled-icon">summarize</span>
            <span>Short Description</span>
          </div>
          <ul className="dp-clinical-short-desc-list">
            {shortDescription.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="dp-clinical-recommendation" aria-label="Clinical recommendation">
        <div className="dp-clinical-recommendation-head">
          <span className="material-symbols-outlined filled-icon">clinical_notes</span>
          <span>Clinical Recommendation</span>
        </div>
        <p>{recommendation}</p>
      </section>
    </div>
  );
}
