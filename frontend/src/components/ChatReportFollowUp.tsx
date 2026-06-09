import { useState } from "react";
import ChatFileAttachment, { ChatAttachment } from "./ChatFileAttachment";
import ChatReportViewModal from "./ChatReportViewModal";

export const REPORT_FOLLOWUP_ACTIONS = [
  {
    label: "Summarize Report",
    message: "Please summarize this medical report in simple terms.",
    display: "Summarize this report in simple terms",
  },
  {
    label: "Explain Abnormal Results",
    message: "Explain any abnormal or out-of-range values in this report.",
    display: "Explain abnormal results in this report",
  },
  {
    label: "Risk Assessment",
    message: "Based on this report, what is my health risk assessment?",
    display: "What is my health risk assessment?",
  },
] as const;

interface Props {
  attachment: ChatAttachment;
  disabled?: boolean;
  onPick: (message: string, display?: string) => void;
}

export default function ChatReportFollowUp({ attachment, disabled, onPick }: Props) {
  const [viewOpen, setViewOpen] = useState(false);

  return (
    <>
      <div className="chat-report-followup">
        <div className="chat-shared-resources">
          <span className="chat-shared-resources-label">Shared Resources</span>
          <ChatFileAttachment
            attachment={attachment}
            variant="ai"
            showView
            onView={() => setViewOpen(true)}
          />
        </div>
        <div className="chat-report-actions">
          {REPORT_FOLLOWUP_ACTIONS.map((action) => (
            <button
              key={action.label}
              type="button"
              className="chat-report-action-btn"
              disabled={disabled}
              onClick={() => onPick(action.message, action.display)}
            >
              {action.label}
            </button>
          ))}
        </div>
      </div>
      {viewOpen && <ChatReportViewModal attachment={attachment} onClose={() => setViewOpen(false)} />}
    </>
  );
}
