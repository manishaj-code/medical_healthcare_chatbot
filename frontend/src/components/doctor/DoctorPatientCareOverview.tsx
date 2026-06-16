import { useState } from "react";
import {
  consultationModeLabel,
  formatDisplayDate,
  formatDoctorTime,
} from "../../utils/doctorPortal";
import type { PatientConsultOverview } from "./DoctorPatientConsultSummary";

interface Props {
  overview: PatientConsultOverview;
}

function truncate(text: string, max = 72): string {
  const cleaned = text.trim();
  if (cleaned.length <= max) return cleaned;
  return `${cleaned.slice(0, max - 1).trim()}…`;
}

function timelineTypeLabel(type: string): string {
  if (type === "report_uploaded") return "Report";
  if (type === "visit_upcoming") return "Upcoming";
  return "Visit";
}

function formatTimelineWhen(item: PatientConsultOverview["timeline"][0]): string {
  if (item.type === "report_uploaded" && item.report?.created_at) {
    return formatDisplayDate(item.report.created_at);
  }
  if (item.date) {
    const when = formatDisplayDate(item.date);
    if (item.time) return `${when} · ${formatDoctorTime(item.time)}`;
    return when;
  }
  return "—";
}

function timelineDetail(item: PatientConsultOverview["timeline"][0]): string | null {
  if (item.type === "visit_completed") {
    if (item.diagnosis) return `Diagnosis: ${truncate(item.diagnosis, 96)}`;
    if (item.treatment_plan) return `Plan: ${truncate(item.treatment_plan, 96)}`;
  }
  if (item.subtitle) return truncate(item.subtitle, 96);
  if (item.linked_report?.summary) return truncate(item.linked_report.summary, 96);
  if (item.report?.summary && item.type === "report_uploaded") {
    return truncate(item.report.summary, 96);
  }
  if (item.type === "visit_upcoming" && item.consultation_mode) {
    return consultationModeLabel(item.consultation_mode);
  }
  return null;
}

function InsightRow({
  icon,
  label,
  items,
}: {
  icon: string;
  label: string;
  items: string[];
}) {
  if (items.length === 0) return null;
  return (
    <div className="dp-care-insight-row">
      <div className="dp-care-insight-label">
        <span className="material-symbols-outlined" aria-hidden>
          {icon}
        </span>
        <span>{label}</span>
      </div>
      <div className="dp-care-insight-chips">
        {items.map((item) => (
          <span key={item} className="dp-care-chip" title={item}>
            {truncate(item, 64)}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function DoctorPatientCareOverview({ overview }: Props) {
  const { rollup, timeline } = overview;
  const [showAllTimeline, setShowAllTimeline] = useState(false);

  const hasContent =
    rollup.completed_visits > 0 || rollup.reports_count > 0 || rollup.upcoming_visits > 0;
  if (!hasContent) return null;

  const visibleTimeline = showAllTimeline ? timeline : timeline.slice(0, 4);
  const hasInsightContent =
    rollup.chief_complaints.length > 0 ||
    rollup.diagnoses.length > 0 ||
    rollup.treatment_plans.length > 0 ||
    rollup.report_summaries.length > 0;

  return (
    <section className="dp-care-summary-v2">
      <header className="dp-care-summary-v2-head">
        <div className="dp-care-summary-v2-title">
          <span className="material-symbols-outlined filled-icon" aria-hidden>
            summarize
          </span>
          <div>
            <h2>Patient consult summary</h2>
            <p>Visits, reports, and clinical highlights in one view.</p>
          </div>
        </div>
        <div className="dp-care-summary-v2-stats" aria-label="Care summary statistics">
          <div className="dp-care-stat-pill">
            <strong>{rollup.completed_visits}</strong>
            <span>Visits</span>
          </div>
          <div className="dp-care-stat-pill">
            <strong>{rollup.reports_count}</strong>
            <span>Reports</span>
          </div>
          <div className="dp-care-stat-pill">
            <strong>{rollup.upcoming_visits}</strong>
            <span>Upcoming</span>
          </div>
        </div>
      </header>

      {rollup.latest_follow_up && (
        <div className="dp-care-followup-banner">
          <span className="material-symbols-outlined" aria-hidden>
            event
          </span>
          <div>
            <span className="dp-care-followup-label">Next follow-up</span>
            <strong>{formatDisplayDate(rollup.latest_follow_up)}</strong>
          </div>
        </div>
      )}

      {hasInsightContent && (
        <div className="dp-care-summary-v2-insights">
          <InsightRow icon="healing" label="Reasons for visit" items={rollup.chief_complaints} />
          <InsightRow icon="diagnosis" label="Diagnoses" items={rollup.diagnoses} />
          <InsightRow icon="assignment" label="Treatment plans" items={rollup.treatment_plans} />
          <InsightRow icon="science" label="Report highlights" items={rollup.report_summaries} />
        </div>
      )}

      {timeline.length > 0 && (
        <div className="dp-care-timeline-v2">
          <div className="dp-care-timeline-v2-head">
            <h3>Recent activity</h3>
            <span className="dp-care-timeline-count">{timeline.length} events</span>
          </div>
          <ol className="dp-care-timeline-v2-list">
            {visibleTimeline.map((item, index) => {
              const detail = timelineDetail(item);
              return (
                <li
                  key={`${item.type}-${item.apt_id ?? item.report?.report_id ?? index}`}
                  className={`dp-care-timeline-v2-item dp-care-timeline-v2-item--${item.type}`}
                >
                  <div className="dp-care-timeline-v2-rail" aria-hidden>
                    <span className="dp-care-timeline-v2-dot" />
                  </div>
                  <article className="dp-care-timeline-v2-card">
                    <div className="dp-care-timeline-v2-meta">
                      <span className={`dp-care-timeline-badge dp-care-timeline-badge--${item.type}`}>
                        {timelineTypeLabel(item.type)}
                      </span>
                      <time>{formatTimelineWhen(item)}</time>
                      {item.apt_id ? <span className="dp-care-timeline-apt">{item.apt_id}</span> : null}
                    </div>
                    <h4>{truncate(item.title, 80)}</h4>
                    {detail ? <p>{detail}</p> : null}
                  </article>
                </li>
              );
            })}
          </ol>
          {timeline.length > 4 && (
            <button
              type="button"
              className="dp-care-timeline-toggle"
              onClick={() => setShowAllTimeline((v) => !v)}
            >
              {showAllTimeline ? "Show fewer events" : `Show all ${timeline.length} events`}
              <span className="material-symbols-outlined" aria-hidden>
                {showAllTimeline ? "expand_less" : "expand_more"}
              </span>
            </button>
          )}
        </div>
      )}
    </section>
  );
}
