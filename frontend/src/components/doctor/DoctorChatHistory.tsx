import { useMemo, useState } from "react";
import { formatChatText } from "../ChatBookingUI";

export interface DoctorChatMessage {
  role: string;
  content: string;
  created_at?: string;
}

export interface DoctorConversation {
  conversation_id: string;
  title: string;
  created_at: string;
  emergency_flag: boolean;
  messages: DoctorChatMessage[];
}

function formatMsgTime(iso?: string): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatSessionDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

interface Props {
  conversations: DoctorConversation[];
  patientName: string;
  onBack?: () => void;
}

export default function DoctorChatHistory({ conversations, patientName, onBack }: Props) {
  const [activeId, setActiveId] = useState(conversations[0]?.conversation_id ?? "");

  const active = useMemo(
    () => conversations.find((c) => c.conversation_id === activeId) ?? conversations[0],
    [conversations, activeId],
  );

  if (conversations.length === 0) {
    return (
      <div className="dp-empty">
        <div className="dp-empty-icon">
          <span className="material-symbols-outlined">forum</span>
        </div>
        <p className="dp-empty-title">No conversations yet</p>
        <p>{patientName} has not used the health chatbot.</p>
        {onBack && (
          <button type="button" className="dp-btn dp-btn--outline dp-btn--sm" onClick={onBack}>
            Back to overview
          </button>
        )}
      </div>
    );
  }

  const patientMsgs = active?.messages.filter((m) => m.role === "user").length ?? 0;
  const aiMsgs = active?.messages.filter((m) => m.role !== "user").length ?? 0;

  return (
    <div className="dp-chat-layout">
      {conversations.length > 1 && (
        <aside className="dp-chat-sessions" aria-label="Conversation list">
          <p className="dp-chat-sessions-label">Sessions</p>
          {conversations.map((conv) => {
            const isActive = conv.conversation_id === active?.conversation_id;
            const preview = conv.messages.find((m) => m.role === "user")?.content ?? "No messages";
            return (
              <button
                key={conv.conversation_id}
                type="button"
                className={`dp-chat-session${isActive ? " dp-chat-session--active" : ""}`}
                onClick={() => setActiveId(conv.conversation_id)}
              >
                <div className="dp-chat-session-top">
                  <span className="dp-chat-session-title">{conv.title}</span>
                  {conv.emergency_flag && <span className="dp-tag dp-tag--critical">!</span>}
                </div>
                <p className="dp-chat-session-preview">{preview.slice(0, 60)}{preview.length > 60 ? "…" : ""}</p>
                <span className="dp-chat-session-date">{formatSessionDate(conv.created_at)}</span>
              </button>
            );
          })}
        </aside>
      )}

      <div className="dp-chat-thread">
        {active && (
          <>
            <header className="dp-chat-session-banner">
              <div className="dp-chat-session-banner-glow" aria-hidden />
              <div className="dp-chat-session-banner-content">
                <p className="dp-chat-session-eyebrow">
                  <span className="material-symbols-outlined">forum</span>
                  Chat session
                </p>
                <div className="dp-chat-session-banner-title-row">
                  <h3 className="dp-chat-session-banner-title">{active.title}</h3>
                  {active.emergency_flag && (
                    <span className="dp-chat-session-emergency">
                      <span className="material-symbols-outlined">warning</span>
                      Emergency
                    </span>
                  )}
                </div>
                <div className="dp-chat-session-stats">
                  <span className="dp-chat-stat-chip">
                    <span className="material-symbols-outlined">calendar_today</span>
                    {formatSessionDate(active.created_at)}
                  </span>
                  <span className="dp-chat-stat-chip">
                    <span className="material-symbols-outlined">chat</span>
                    {active.messages.length} messages
                  </span>
                  <span className="dp-chat-stat-chip">
                    <span className="material-symbols-outlined">person</span>
                    {patientMsgs} patient
                  </span>
                  <span className="dp-chat-stat-chip">
                    <span className="material-symbols-outlined">smart_toy</span>
                    {aiMsgs} AI
                  </span>
                </div>
              </div>
            </header>

            <div className="dp-chat-transcript-divider">
              <span>Conversation transcript</span>
            </div>

            <div className="dp-chat-messages custom-scrollbar">
              {active.messages.map((m, i) => {
                const isUser = m.role === "user";
                const time = formatMsgTime(m.created_at);
                return (
                  <div
                    key={`${active.conversation_id}-${i}`}
                    className={`dp-chat-bubble-row${isUser ? " dp-chat-bubble-row--patient" : " dp-chat-bubble-row--ai"}`}
                  >
                    <div className={`dp-chat-avatar${isUser ? " dp-chat-avatar--patient" : " dp-chat-avatar--ai"}`}>
                      <span className="material-symbols-outlined filled-icon">
                        {isUser ? "person" : "smart_toy"}
                      </span>
                    </div>
                    <div className="dp-chat-bubble-wrap">
                      <div className="dp-chat-bubble-label">
                        <span>{isUser ? "Patient" : "AI Assistant"}</span>
                        {time && <time dateTime={m.created_at}>{time}</time>}
                      </div>
                      <div className={`dp-chat-bubble${isUser ? " dp-chat-bubble--patient" : " dp-chat-bubble--ai"}`}>
                        <div className="dp-chat-bubble-text">{formatChatText(m.content)}</div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
