import { formatChatText } from "../ChatBookingUI";
import type { HealthVital } from "../../utils/healthVitals";
import { parseReportAnalysis, reportFileIcon } from "../../utils/reportDisplay";

export interface DoctorReportRow {
  id: string;
  analysis: Record<string, unknown> | null;
  created_at?: string | null;
}

function formatReportDate(iso: string | null | undefined): string {
  if (!iso) return "Recently uploaded";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function abnormalClass(flag?: string): string {
  const f = (flag ?? "").toUpperCase();
  if (f === "HIGH") return "dp-lab-flag--high";
  if (f === "LOW") return "dp-lab-flag--low";
  return "dp-lab-flag--neutral";
}

export default function DoctorPatientLabSection({
  vitals,
  reports,
}: {
  vitals: HealthVital[];
  reports: DoctorReportRow[];
}) {
  if (!vitals.length && !reports.length) return null;

  return (
    <section className="dp-overview-labs">
      <div className="dp-panel-head">
        <div>
          <h2 className="dp-panel-title">Lab &amp; vitals</h2>
          <p className="dp-panel-desc" style={{ margin: "4px 0 0" }}>
            Uploaded patient reports with extracted vitals and AI summaries.
          </p>
        </div>
      </div>

      {vitals.length > 0 && (
        <div className="dp-overview-vitals-strip">
          {vitals.map((vital) => (
            <article key={vital.key} className="dp-overview-vital-chip">
              <span className="dp-overview-vital-label">{vital.label}</span>
              <strong className="dp-overview-vital-value">
                {vital.value_secondary ? `${vital.value}/${vital.value_secondary}` : vital.display}
                <span className="dp-overview-vital-unit">{vital.unit}</span>
              </strong>
              {vital.source_filename && (
                <span className="dp-overview-vital-source">{vital.source_filename}</span>
              )}
            </article>
          ))}
        </div>
      )}

      {reports.length > 0 ? (
        <div className="dp-overview-lab-grid">
          {reports.map((report) => {
            const parsed = parseReportAnalysis(report.id, report.analysis);
            return (
              <article key={report.id} className="dp-overview-lab-card">
                <div className="dp-overview-lab-card-head">
                  <span className="dp-overview-lab-icon material-symbols-outlined">
                    {reportFileIcon(parsed.filename)}
                  </span>
                  <div>
                    <h3 title={parsed.filename}>{parsed.filename}</h3>
                    <p>{formatReportDate(report.created_at)}</p>
                  </div>
                </div>

                {parsed.summary ? (
                  <p className="dp-overview-lab-summary">{formatChatText(parsed.summary)}</p>
                ) : (
                  <p className="dp-overview-lab-summary dp-overview-lab-summary--muted">
                    No AI summary available for this report yet.
                  </p>
                )}

                {parsed.abnormal.length > 0 && (
                  <div className="dp-overview-lab-flags">
                    {parsed.abnormal.slice(0, 4).map((item, idx) => (
                      <span
                        key={`${item.test}-${idx}`}
                        className={`dp-lab-flag ${abnormalClass(item.flag)}`}
                      >
                        {item.test}: {item.value} ({item.flag})
                      </span>
                    ))}
                    {parsed.abnormal.length > 4 && (
                      <span className="dp-lab-flag dp-lab-flag--neutral">
                        +{parsed.abnormal.length - 4} more
                      </span>
                    )}
                  </div>
                )}
              </article>
            );
          })}
        </div>
      ) : (
        vitals.length > 0 && (
          <p className="dp-muted-note" style={{ margin: 0 }}>
            Vitals were extracted from uploaded reports. No additional report summaries on file.
          </p>
        )
      )}
    </section>
  );
}
