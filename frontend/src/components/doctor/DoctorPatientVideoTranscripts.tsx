import { Link } from "react-router-dom";
import { formatDisplayDate, formatDoctorTime } from "../../utils/doctorPortal";

export interface VideoTranscriptRow {
  appointment_id: string;
  apt_id: string;
  date: string;
  time: string;
  status: string;
  transcript_preview?: string | null;
  transcript_summary?: string | null;
  transcript_segment_count?: number;
  segment_count?: number;
  has_transcript?: boolean;
}

interface Props {
  rows: VideoTranscriptRow[];
  loading?: boolean;
  patientName: string;
}

function statusLabel(status: string): string {
  const s = status.toLowerCase();
  if (s === "completed") return "Completed";
  if (s === "confirmed") return "Confirmed";
  if (s === "cancelled") return "Cancelled";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function TranscriptSkeletonLines() {
  return (
    <div className="dp-video-transcript-skeleton-lines" aria-hidden>
      <span />
      <span />
      <span className="dp-video-transcript-skeleton-lines--short" />
    </div>
  );
}

export default function DoctorPatientVideoTranscripts({ rows, loading, patientName }: Props) {
  return (
    <section className="dp-glass dp-video-transcripts-panel" aria-label="Video consultation transcripts">
      <header className="dp-panel-head">
        <div>
          <h2 className="dp-panel-title">Video consultation transcripts</h2>
          <p className="dp-panel-desc" style={{ margin: "4px 0 0" }}>
            Doctor–patient video discussions for {patientName}. Excerpts and AI in-visit summaries
            from completed and in-progress calls.
          </p>
        </div>
      </header>

      {loading && (
        <div className="dp-video-transcript-list">
          {[0, 1].map((i) => (
            <article key={i} className="dp-video-transcript-card dp-video-transcript-card--skeleton">
              <div className="dp-video-transcript-card-head">
                <span className="dp-skeleton-block dp-skeleton-block--title" />
                <span className="dp-skeleton-block dp-skeleton-block--pill" />
              </div>
              <TranscriptSkeletonLines />
            </article>
          ))}
        </div>
      )}

      {!loading && rows.length === 0 && (
        <div className="dp-video-transcript-empty">
          <span className="material-symbols-outlined">videocam_off</span>
          <p>No video consultations on record for this patient yet.</p>
        </div>
      )}

      {!loading && rows.length > 0 && (
        <div className="dp-video-transcript-list">
          {rows.map((row) => {
            const segmentCount = row.transcript_segment_count ?? row.segment_count ?? 0;
            const hasContent = Boolean(
              row.has_transcript || row.transcript_preview || row.transcript_summary,
            );
            return (
              <article
                key={row.appointment_id}
                className={`dp-video-transcript-card${hasContent ? "" : " dp-video-transcript-card--pending"}`}
              >
                <div className="dp-video-transcript-card-head">
                  <div>
                    <div className="dp-video-transcript-card-meta">
                      <span className="dp-table-apt-id">{row.apt_id}</span>
                      <span className="dp-muted-note">
                        {formatDisplayDate(row.date)} · {formatDoctorTime(row.time)}
                      </span>
                      <span className={`dp-tag dp-tag--${row.status === "completed" ? "success" : "info"}`}>
                        {statusLabel(row.status)}
                      </span>
                    </div>
                    <h3 className="dp-video-transcript-card-title">Video consultation</h3>
                  </div>
                  {(row.status === "confirmed" || row.status === "completed") && (
                    <Link
                      to={`/doctor/consultation/${row.appointment_id}`}
                      className="dp-btn dp-btn--sm dp-btn--outline"
                    >
                      Open visit
                    </Link>
                  )}
                </div>

                {hasContent ? (
                  <div className="dp-video-transcript-card-body">
                    {row.transcript_summary && (
                      <p className="dp-video-transcript-summary">{row.transcript_summary}</p>
                    )}
                    {row.transcript_preview && (
                      <blockquote className="dp-video-transcript-preview">{row.transcript_preview}</blockquote>
                    )}
                    {segmentCount > 0 && (
                      <p className="dp-muted-note">{segmentCount} transcript segments</p>
                    )}
                  </div>
                ) : (
                  <div className="dp-video-transcript-card-body dp-video-transcript-card-body--placeholder">
                    <p className="dp-muted-note">
                      {row.status === "completed"
                        ? "No transcript was captured for this visit."
                        : "Transcript will populate during or after the video call."}
                    </p>
                    <TranscriptSkeletonLines />
                  </div>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
