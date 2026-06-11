import {
  type ClinicalSummaryFields,
  type ConsultClinicalSource,
  buildMergedClinicalFields,
  isStructuredClinicalSummaryText,
} from "../../utils/clinicalSummaryFormat";
import StructuredClinicalSummary from "./StructuredClinicalSummary";

interface Props {
  summaryText: string;
  fields?: ClinicalSummaryFields;
  consult?: ConsultClinicalSource | null;
  variant?: "full" | "compact" | "list";
  title?: string;
  loading?: boolean;
}

export default function ClinicalSummaryPanel({
  summaryText,
  fields,
  consult,
  variant = "full",
  title = "AI Clinical Summary",
  loading = false,
}: Props) {
  const isClinical = isStructuredClinicalSummaryText(summaryText);
  const resolvedFields = fields ?? buildMergedClinicalFields(summaryText, consult ?? null);
  const useStructured =
    Boolean(fields) ||
    isClinical ||
    resolvedFields.symptomLabels.length > 0 ||
    Boolean(consult?.detected_symptoms?.length);

  return (
    <div className={`dp-clinical-panel dp-clinical-panel--${variant}`}>
      <div className="dp-clinical-panel-head">
        <div className="dp-panel-icon">
          <span className="material-symbols-outlined filled-icon">auto_awesome</span>
        </div>
        <h2 className="dp-clinical-panel-title">{title}</h2>
      </div>

      {loading ? (
        <p className="dp-clinical-panel-loading">Loading clinical summary…</p>
      ) : !useStructured ? (
        <div className="dp-clinical-fallback-note">
          <p>{summaryText}</p>
        </div>
      ) : (
        <StructuredClinicalSummary fields={resolvedFields} variant={variant} />
      )}
    </div>
  );
}
