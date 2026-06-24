import { useEffect, useState } from "react";
import { api } from "../api/client";
import { ChatAttachment } from "./ChatFileAttachment";
import { ReportModalSkeleton } from "./skeleton";

interface ReportData {
  analysis?: {
    summary?: string;
    abnormal?: { test?: string; value?: string; flag?: string }[];
  };
  ocr_text?: string;
}

interface Props {
  attachment: ChatAttachment;
  onClose: () => void;
}

export default function ChatReportViewModal({ attachment, onClose }: Props) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [report, setReport] = useState<ReportData | null>(null);

  useEffect(() => {
    if (!attachment.report_id) {
      setError("Report ID not available.");
      setLoading(false);
      return;
    }
    let active = true;
    api<ReportData>(`/api/v1/reports/${attachment.report_id}`)
      .then((data) => {
        if (active) setReport(data);
      })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "Could not load report");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [attachment.report_id]);

  return (
    <div className="chat-report-modal" role="dialog" aria-modal="true" aria-labelledby="report-view-title">
      <button type="button" className="chat-report-modal-backdrop" onClick={onClose} aria-label="Close" />
      <div className="chat-report-modal-card">
        <header className="chat-report-modal-head">
          <div>
            <h3 id="report-view-title">{attachment.filename}</h3>
            <p>Clinical report details</p>
          </div>
          <button type="button" className="chat-report-modal-close" onClick={onClose} aria-label="Close">
            <span className="material-symbols-outlined">close</span>
          </button>
        </header>

        {loading && <ReportModalSkeleton />}
        {error && <p className="chat-report-modal-error">{error}</p>}

        {!loading && !error && report && (
          <div className="chat-report-modal-body">
            {report.analysis?.summary && (
              <section>
                <h4>Summary</h4>
                <p>{report.analysis.summary}</p>
              </section>
            )}
            {report.analysis?.abnormal && report.analysis.abnormal.length > 0 && (
              <section>
                <h4>Flagged values</h4>
                <ul>
                  {report.analysis.abnormal.map((item, idx) => (
                    <li key={`${item.test}-${idx}`}>
                      <strong>{item.test || "Test"}</strong>: {item.value || "—"}
                      {item.flag ? ` (${item.flag})` : ""}
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {report.ocr_text && (
              <section>
                <h4>Extracted text</h4>
                <pre>{report.ocr_text}</pre>
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
