import { useState } from "react";
import ChatFileAttachment, { ChatAttachment } from "./ChatFileAttachment";
import ChatReportViewModal from "./ChatReportViewModal";

export const REPORT_FOLLOWUP_ACTIONS = [
  {
    label: "Explain in simple language",
    message: "Please summarize this medical report in simple terms.",
    display: "Explain this report in simple language",
  },
  {
    label: "Book appointment",
    message: "I'd like to book an appointment based on this report.",
    display: "Book appointment",
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
