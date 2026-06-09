import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { formatChatText } from "../../components/ChatBookingUI";
import ChatReportViewModal from "../../components/ChatReportViewModal";
import { ChatAttachment } from "../../components/ChatFileAttachment";
import { formatChatDateLabel } from "../../utils/chatConversations";

interface ReportListItem {
  id: string;
  filename: string;
  created_at: string | null;
  has_analysis: boolean;
  summary?: string | null;
  abnormal_count: number;
  abnormal?: { test?: string; value?: string; flag?: string }[];
}

function fileIcon(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() || "";
  if (ext === "pdf") return "picture_as_pdf";
  if (["png", "jpg", "jpeg", "webp", "gif", "bmp", "tif", "tiff"].includes(ext)) return "image";
  if (ext === "docx") return "description";
  if (["xlsx", "csv", "tsv"].includes(ext)) return "table_chart";
  return "attach_file";
}

export default function PatientReports() {
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewReport, setViewReport] = useState<ChatAttachment | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    api<ReportListItem[]>("/api/v1/reports")
      .then(setReports)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const refresh = () => load();
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [load]);

  return (
    <div className="patient-dashboard">
      <section className="pd-section pd-reports-page">
        <div className="pd-section-head pd-reports-head">
          <div>
            <h3>My Reports</h3>
            <p className="pd-section-sub">All uploaded medical documents with AI analysis summaries</p>
          </div>
          <div className="pd-reports-actions">
            <button type="button" className="pd-outline-btn" onClick={load} disabled={loading}>
              Refresh
            </button>
            <Link to="/chat" className="pd-cta-btn pd-cta-btn--compact">
              <span className="material-symbols-outlined">upload_file</span>
              Upload Report
            </Link>
          </div>
        </div>

        {loading && <p className="pd-muted">Loading reports...</p>}

        {!loading && reports.length === 0 && (
          <div className="pd-empty-card pd-reports-empty">
            <span className="material-symbols-outlined pd-empty-icon">description</span>
            <p>No reports uploaded yet.</p>
            <p className="pd-reports-empty-hint">
              Upload a lab report or medical document in AI Consultation to see analysis here.
            </p>
            <Link to="/chat" className="pd-outline-btn">Go to AI Consultation</Link>
          </div>
        )}

        <div className="pd-reports-grid">
          {reports.map((report) => (
            <article key={report.id} className="pd-report-card">
              <div className="pd-report-card-top">
                <div className="pd-report-icon" aria-hidden="true">
                  <span className="material-symbols-outlined">{fileIcon(report.filename)}</span>
                </div>
                <div className="pd-report-meta">
                  <h4 title={report.filename}>{report.filename}</h4>
                  <span>
                    {report.created_at
                      ? formatChatDateLabel(report.created_at)
                      : "Recently uploaded"}
                    {report.has_analysis ? " · Analyzed" : " · Pending analysis"}
                  </span>
                </div>
              </div>

              {report.summary ? (
                <p className="pd-report-summary">{formatChatText(report.summary)}</p>
              ) : (
                <p className="pd-report-summary pd-report-summary--muted">
                  Analysis not available yet. Open in consultation to process this report.
                </p>
              )}

              {report.abnormal && report.abnormal.length > 0 && (
                <div className="pd-report-flags">
                  {report.abnormal.map((item, idx) => (
                    <span key={`${item.test}-${idx}`} className="pd-report-flag">
                      {item.test}: {item.value} ({item.flag})
                    </span>
                  ))}
                </div>
              )}

              <div className="pd-report-card-actions">
                <button
                  type="button"
                  className="pd-outline-btn"
                  onClick={() =>
                    setViewReport({
                      type: "report",
                      report_id: report.id,
                      filename: report.filename,
                    })
                  }
                >
                  View Summary
                </button>
                <Link
                  to="/chat"
                  state={{
                    promptMessage: `Please explain the results in my report "${report.filename}" in simple terms.`,
                  }}
                  className="pd-link-btn"
                >
                  Discuss in Chat
                </Link>
              </div>
            </article>
          ))}
        </div>
      </section>

      {viewReport && (
        <ChatReportViewModal attachment={viewReport} onClose={() => setViewReport(null)} />
      )}
    </div>
  );
}
