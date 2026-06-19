import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import {
  consultationModeIcon,
  consultationModeLabel,
} from "../../utils/consultationMode";
import { formatDisplayDate, formatDoctorDisplayName, formatDoctorTime } from "../../utils/doctorPortal";
import { HealthRecordsSkeleton } from "../../components/skeleton";

interface ConsultationRecord {
  id: string;
  appointment_date: string;
  appointment_time: string;
  doctor_name: string;
  consultation_mode: string;
  chief_complaint: string | null;
  clinical_findings?: string | null;
  diagnosis: string | null;
  treatment_plan: string | null;
  follow_up_date: string | null;
  prescription_items: {
    medicine_name: string;
    strength?: string | null;
    frequency?: string | null;
    duration?: string | null;
  }[];
  lab_orders: { test_name: string }[];
  apt_id: string;
}

function recordSnippet(record: ConsultationRecord): string {
  const parts: string[] = [];
  if (record.chief_complaint) parts.push(record.chief_complaint);
  if (record.diagnosis) parts.push(record.diagnosis);
  return parts.join(" · ");
}

function buildCareSummary(records: ConsultationRecord[]): {
  visitCount: number;
  diagnoses: string[];
  complaints: string[];
  treatments: string[];
  latestFollowUp: string | null;
} {
  const diagnoses = [
    ...new Set(records.map((r) => r.diagnosis?.trim()).filter(Boolean) as string[]),
  ];
  const complaints = [
    ...new Set(records.map((r) => r.chief_complaint?.trim()).filter(Boolean) as string[]),
  ];
  const treatments = [
    ...new Set(records.map((r) => r.treatment_plan?.trim()).filter(Boolean) as string[]),
  ];
  const latestFollowUp = records.find((r) => r.follow_up_date)?.follow_up_date ?? null;
  return {
    visitCount: records.length,
    diagnoses: diagnoses.slice(0, 5),
    complaints: complaints.slice(0, 5),
    treatments: treatments.slice(0, 3),
    latestFollowUp,
  };
}

function CareSummaryPanel({ records }: { records: ConsultationRecord[] }) {
  const summary = buildCareSummary(records);
  const [showAllInsights, setShowAllInsights] = useState(false);

  if (summary.visitCount === 0) return null;

  const latest = records[0];
  const visibleTreatments = showAllInsights ? summary.treatments : summary.treatments.slice(0, 2);

  return (
    <section className="phr-care-summary-v2">
      <header className="phr-care-summary-v2-head">
        <div className="phr-care-summary-v2-title">
          <span className="material-symbols-outlined" aria-hidden>
            summarize
          </span>
          <div>
            <h2>Your care summary</h2>
            <p>
              Highlights from {summary.visitCount} completed visit{summary.visitCount === 1 ? "" : "s"}.
            </p>
          </div>
        </div>
        <div className="phr-care-summary-v2-stat" aria-label="Completed visits">
          <strong>{summary.visitCount}</strong>
          <span>Visits</span>
        </div>
      </header>

      {summary.latestFollowUp && (
        <div className="phr-care-followup-banner">
          <span className="material-symbols-outlined" aria-hidden>
            event
          </span>
          <div>
            <span>Next follow-up</span>
            <strong>{formatDisplayDate(summary.latestFollowUp)}</strong>
          </div>
        </div>
      )}

      {latest && (
        <article className="phr-care-latest-visit">
          <span className="phr-care-latest-label">Most recent visit</span>
          <div className="phr-care-latest-main">
            <div>
              <strong>{formatDoctorDisplayName(latest.doctor_name)}</strong>
              <span>
                {formatDisplayDate(latest.appointment_date)} · {formatDoctorTime(latest.appointment_time)}
              </span>
            </div>
            <span className="phr-care-latest-apt">{latest.apt_id}</span>
          </div>
          {(latest.chief_complaint || latest.diagnosis) && (
            <p className="phr-care-latest-snippet">
              {[latest.chief_complaint, latest.diagnosis].filter(Boolean).join(" · ")}
            </p>
          )}
        </article>
      )}

      <div className="phr-care-summary-v2-insights">
        {summary.complaints.length > 0 && (
          <div className="phr-care-insight-row">
            <div className="phr-care-insight-label">
              <span className="material-symbols-outlined" aria-hidden>
                healing
              </span>
              <span>Reasons for visit</span>
            </div>
            <div className="phr-care-chips">
              {summary.complaints.map((c) => (
                <span key={c} className="phr-care-chip">
                  {c}
                </span>
              ))}
            </div>
          </div>
        )}

        {summary.diagnoses.length > 0 && (
          <div className="phr-care-insight-row">
            <div className="phr-care-insight-label">
              <span className="material-symbols-outlined" aria-hidden>
                diagnosis
              </span>
              <span>Diagnoses</span>
            </div>
            <div className="phr-care-chips">
              {summary.diagnoses.map((d) => (
                <span key={d} className="phr-care-chip phr-care-chip--diagnosis">
                  {d}
                </span>
              ))}
            </div>
          </div>
        )}

        {visibleTreatments.length > 0 && (
          <div className="phr-care-insight-row phr-care-insight-row--stacked">
            <div className="phr-care-insight-label">
              <span className="material-symbols-outlined" aria-hidden>
                assignment
              </span>
              <span>Treatment plans</span>
            </div>
            <ul className="phr-care-plan-list">
              {visibleTreatments.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
            {summary.treatments.length > 2 && (
              <button
                type="button"
                className="phr-care-toggle"
                onClick={() => setShowAllInsights((v) => !v)}
              >
                {showAllInsights
                  ? "Show fewer plans"
                  : `Show ${summary.treatments.length - 2} more plan${summary.treatments.length - 2 === 1 ? "" : "s"}`}
              </button>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function HealthRecordCard({ record }: { record: ConsultationRecord }) {
  const [open, setOpen] = useState(false);
  const snippet = recordSnippet(record);
  const modeLabel = consultationModeLabel(record.consultation_mode);
  const modeIcon = consultationModeIcon(record.consultation_mode);

  return (
    <article className={`phr-card${open ? " phr-card--open" : ""}`}>
      <div className="phr-card-head">
        <div className="phr-card-doctor">
          <span className="phr-card-avatar" aria-hidden>
            <span className="material-symbols-outlined">medical_services</span>
          </span>
          <div className="phr-card-doctor-text">
            <strong>{formatDoctorDisplayName(record.doctor_name)}</strong>
            <span className="phr-card-apt">{record.apt_id}</span>
          </div>
        </div>

        <button
          type="button"
          className="phr-card-expand"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-label={open ? "Hide consultation details" : "Show consultation details"}
        >
          {!open && (
            <span className="phr-card-snippet" title={snippet || "View consultation details"}>
              {snippet || "View consultation details"}
            </span>
          )}
          <span className="phr-card-expand-trail">
            <span className="phr-card-meta">
              <span className="phr-card-date">
                {formatDisplayDate(record.appointment_date)} · {formatDoctorTime(record.appointment_time)}
              </span>
              <span className="phr-card-mode">
                <span className="material-symbols-outlined">{modeIcon}</span>
                {modeLabel}
              </span>
              <span className="phr-card-status">Completed</span>
            </span>
            <span
              className={`material-symbols-outlined phr-card-chevron${open ? " phr-card-chevron--open" : ""}`}
              aria-hidden
            >
              expand_more
            </span>
          </span>
        </button>
      </div>

      {open && (
        <div className="phr-card-body">
          <div className="phr-detail-grid">
            <section className="phr-detail-block">
              <h3>
                <span className="material-symbols-outlined">clinical_notes</span>
                Chief complaint
              </h3>
              <p>{record.chief_complaint || "Not recorded"}</p>
            </section>
            {record.clinical_findings ? (
              <section className="phr-detail-block">
                <h3>
                  <span className="material-symbols-outlined">description</span>
                  Visit notes
                </h3>
                <p className="phr-detail-pre">{record.clinical_findings}</p>
              </section>
            ) : null}
            <section className="phr-detail-block phr-detail-block--highlight">
              <h3>
                <span className="material-symbols-outlined">diagnosis</span>
                Diagnosis
              </h3>
              <p>{record.diagnosis || "Not recorded"}</p>
            </section>
            <section className="phr-detail-block phr-detail-block--wide">
              <h3>
                <span className="material-symbols-outlined">assignment</span>
                Treatment plan
              </h3>
              <p className="phr-multiline">{record.treatment_plan || "Not recorded"}</p>
            </section>
          </div>

          {(record.prescription_items.length > 0 || record.lab_orders.length > 0) && (
            <div className="phr-detail-grid phr-detail-grid--secondary">
              {record.prescription_items.length > 0 && (
                <section className="phr-detail-block">
                  <h3>
                    <span className="material-symbols-outlined">medication</span>
                    Prescription
                  </h3>
                  <ul className="phr-med-list">
                    {record.prescription_items.map((m) => (
                      <li key={m.medicine_name}>
                        <strong>{m.medicine_name}</strong>
                        <span>
                          {[m.strength, m.frequency, m.duration].filter(Boolean).join(" · ") ||
                            "As directed"}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              {record.lab_orders.length > 0 && (
                <section className="phr-detail-block">
                  <h3>
                    <span className="material-symbols-outlined">science</span>
                    Diagnostic tests
                  </h3>
                  <ul className="phr-tag-list">
                    {record.lab_orders.map((l) => (
                      <li key={l.test_name}>{l.test_name}</li>
                    ))}
                  </ul>
                </section>
              )}
            </div>
          )}

          {record.follow_up_date && (
            <div className="phr-followup">
              <span className="material-symbols-outlined">event</span>
              <span>
                Follow-up scheduled for <strong>{formatDisplayDate(record.follow_up_date)}</strong>
              </span>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

export default function HealthRecords() {
  const [records, setRecords] = useState<ConsultationRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<ConsultationRecord[]>("/api/v1/patients/me/consultations")
      .then(setRecords)
      .catch(() => setRecords([]))
      .finally(() => setLoading(false));
  }, []);

  const latestDate = useMemo(
    () => (records.length > 0 ? formatDisplayDate(records[0].appointment_date) : null),
    [records],
  );

  return (
    <div className="patient-health-records">
      <header className="phr-header">
        <div>
          <h1>My Health Records</h1>
          <p>Your completed consultations — in-person, video, and virtual visits.</p>
        </div>
        {!loading && records.length > 0 && (
          <div className="phr-stats">
            <div className="phr-stat">
              <span className="phr-stat-value">{records.length}</span>
              <span className="phr-stat-label">Completed visits</span>
            </div>
            {latestDate && (
              <div className="phr-stat">
                <span className="phr-stat-value phr-stat-value--sm">{latestDate}</span>
                <span className="phr-stat-label">Most recent</span>
              </div>
            )}
          </div>
        )}
      </header>

      {loading ? (
        <HealthRecordsSkeleton />
      ) : records.length === 0 ? (
        <div className="phr-empty">
          <span className="material-symbols-outlined">folder_open</span>
          <strong>No completed consultations yet</strong>
          <p>After your doctor completes a visit, your diagnosis, prescription, and follow-up will appear here.</p>
          <Link to="/appointments" className="phr-empty-btn">
            View appointments
          </Link>
        </div>
      ) : (
        <>
          <CareSummaryPanel records={records} />
          <div className="phr-list">
            {records.map((r) => (
              <HealthRecordCard key={r.id} record={r} />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
