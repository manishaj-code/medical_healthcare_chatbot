import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../../api/client";
import { formatChatText } from "../ChatBookingUI";
import { resolveDisplayText } from "../../utils/chatTokens";
import type {
  TranscriptAiSuggestions,
  TranscriptSegment,
  TranscriptSnapshot,
} from "../../types/consultationTranscript";
import type { DoctorConversation } from "./DoctorChatHistory";
import ConsultationVisitSummaries from "./ConsultationVisitSummaries";

type PrepTab = "summary" | "chats" | "transcript";

interface Props {
  appointmentId: string;
  patientId: string;
  patientName: string;
  isVideo: boolean;
  reportVisit: boolean;
  canStart: boolean;
  saving: boolean;
  onStartConsultation: () => void;
  onTranscriptAnalyze?: (suggestions: TranscriptAiSuggestions) => void;
  onApplyTranscriptToForm?: (suggestions: TranscriptAiSuggestions) => void;
  transcriptApplyQueued?: boolean;
  children: ReactNode;
}

function formatWhen(iso?: string | null): string | null {
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

function PreVisitChatsTab({
  patientId,
  patientName,
}: {
  patientId: string;
  patientName: string;
}) {
  const [conversations, setConversations] = useState<DoctorConversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeId, setActiveId] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void api<DoctorConversation[]>(`/api/v1/doctor/patients/${patientId}/conversations`)
      .then((rows) => {
        if (cancelled) return;
        setConversations(rows);
        setActiveId(rows[0]?.conversation_id ?? "");
      })
      .catch(() => {
        if (!cancelled) setConversations([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [patientId]);

  const active = useMemo(
    () => conversations.find((c) => c.conversation_id === activeId) ?? conversations[0],
    [conversations, activeId],
  );

  if (loading) {
    return (
      <div className="dp-consult-prep-tab-empty">
        <div className="dp-spinner" />
        <p>Loading chat history…</p>
      </div>
    );
  }

  if (conversations.length === 0) {
    return (
      <div className="dp-consult-prep-tab-empty">
        <span className="material-symbols-outlined">forum</span>
        <p className="dp-consult-prep-tab-empty-title">No AI chats yet</p>
        <p>{patientName} has not used the health chatbot before this visit.</p>
      </div>
    );
  }

  return (
    <div className="dp-consult-prep-chats">
      {conversations.length > 1 && (
        <aside className="dp-consult-prep-chat-sessions" aria-label="Chat sessions">
          {conversations.map((conv) => {
            const isActive = conv.conversation_id === active?.conversation_id;
            const previewRaw = conv.messages.find((m) => m.role === "user")?.content ?? "";
            const preview = resolveDisplayText(previewRaw);
            return (
              <button
                key={conv.conversation_id}
                type="button"
                className={`dp-consult-prep-chat-session${isActive ? " dp-consult-prep-chat-session--active" : ""}`}
                onClick={() => setActiveId(conv.conversation_id)}
              >
                <span className="dp-consult-prep-chat-session-title">{conv.title}</span>
                {preview && (
                  <span className="dp-consult-prep-chat-session-preview">
                    {preview.slice(0, 72)}
                    {preview.length > 72 ? "…" : ""}
                  </span>
                )}
                <span className="dp-consult-prep-chat-session-meta">
                  {formatWhen(conv.created_at)} · {conv.messages.length} msgs
                </span>
              </button>
            );
          })}
        </aside>
      )}

      <div className="dp-consult-prep-chat-thread custom-scrollbar">
        {active && (
          <>
            <header className="dp-consult-prep-chat-head">
              <h3>{active.title}</h3>
              <p>
                {formatWhen(active.created_at)} · {active.messages.length} messages
                {active.emergency_flag && (
                  <span className="dp-tag dp-tag--critical" style={{ marginLeft: 8 }}>
                    Emergency
                  </span>
                )}
              </p>
            </header>
            <div className="dp-consult-prep-chat-messages">
              {active.messages.map((m, i) => {
                const isUser = m.role === "user";
                const time = formatWhen(m.created_at);
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
                        <div className="dp-chat-bubble-text">
                          {formatChatText(isUser ? resolveDisplayText(m.content) : m.content)}
                        </div>
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

function PreVisitTranscriptTab({
  appointmentId,
  isVideo,
}: {
  appointmentId: string;
  isVideo: boolean;
}) {
  const [snapshot, setSnapshot] = useState<TranscriptSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadTranscript = useCallback(async () => {
    try {
      const data = await api<TranscriptSnapshot>(
        `/api/v1/doctor/appointments/${appointmentId}/transcript`,
      );
      setSnapshot(data);
      setError("");
      return data;
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not load transcript");
      return null;
    } finally {
      setLoading(false);
    }
  }, [appointmentId]);

  useEffect(() => {
    void loadTranscript();
  }, [loadTranscript]);

  useEffect(() => {
    if (snapshot?.session?.status !== "active") return undefined;
    const id = window.setInterval(() => void loadTranscript(), 4000);
    return () => window.clearInterval(id);
  }, [snapshot?.session?.status, loadTranscript]);

  const segments = snapshot?.segments ?? [];
  const session = snapshot?.session;
  const hasContent = segments.length > 0 || Boolean(session?.full_transcript_text?.trim());

  if (loading) {
    return (
      <div className="dp-consult-prep-tab-empty">
        <div className="dp-spinner" />
        <p>Loading transcript…</p>
      </div>
    );
  }

  if (error && !session) {
    return (
      <div className="dp-consult-prep-tab-empty">
        <span className="material-symbols-outlined">error</span>
        <p className="dp-consult-prep-tab-empty-title">Transcript unavailable</p>
        <p>{error}</p>
      </div>
    );
  }

  if (!hasContent) {
    return (
      <div className="dp-consult-prep-tab-empty">
        <span className="material-symbols-outlined">subtitles</span>
        <p className="dp-consult-prep-tab-empty-title">No transcript yet</p>
        <p>
          {isVideo
            ? "Start the video consultation to capture a live transcript. Segments will appear here as the call progresses."
            : "Start a video call from this consultation to capture a live transcript."}
        </p>
      </div>
    );
  }

  return (
    <div className="dp-consult-prep-transcript">
      <header className="dp-consult-prep-transcript-head">
        <div>
          <h3>Video call transcript</h3>
          <p>
            {session?.status === "active" ? "Live — updating" : "Recorded session"}
            {session?.started_at && ` · Started ${formatWhen(session.started_at)}`}
            {segments.length > 0 && ` · ${segments.length} segments`}
          </p>
        </div>
        {session?.status === "active" && (
          <span className="dp-consult-prep-transcript-live">
            <span className="dp-consult-prep-transcript-live-dot" aria-hidden />
            Live
          </span>
        )}
      </header>

      <p className="dp-consult-prep-transcript-analyze-hint">
        The <strong>Summary</strong> tab shows an in-visit AI summary that updates automatically from
        this transcript.
      </p>

      <div className="dp-consult-prep-transcript-feed custom-scrollbar">
        {segments.length > 0
          ? segments.map((seg: TranscriptSegment) => (
              <div
                key={seg.id}
                className={`video-transcript-line video-transcript-line--${seg.speaker_role}`}
              >
                <span className="video-transcript-speaker">{seg.speaker_label || seg.speaker_role}</span>
                <p>{seg.text}</p>
              </div>
            ))
          : session?.full_transcript_text
              ?.split("\n")
              .filter(Boolean)
              .map((line, i) => (
                <div key={`line-${i}`} className="video-transcript-line">
                  <p>{line}</p>
                </div>
              ))}
      </div>
    </div>
  );
}

export default function PreVisitPrepPanel({
  appointmentId,
  patientId,
  patientName,
  isVideo,
  reportVisit,
  canStart,
  saving,
  onStartConsultation,
  onTranscriptAnalyze,
  onApplyTranscriptToForm,
  transcriptApplyQueued,
  children,
}: Props) {
  const [tab, setTab] = useState<PrepTab>("summary");

  const tabs: { id: PrepTab; label: string; icon: string }[] = [
    { id: "summary", label: "Summary", icon: "auto_awesome" },
    { id: "chats", label: "AI chats", icon: "forum" },
    { id: "transcript", label: "Transcript", icon: "subtitles" },
  ];

  return (
    <section className="dp-consult-prep-stage">
      <nav className="dp-tabs dp-consult-prep-tabs" aria-label="Pre-visit review">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`dp-tab${tab === t.id ? " dp-tab--active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            <span className="material-symbols-outlined">{t.icon}</span>
            {t.label}
            {t.id === "transcript" && isVideo && (
              <span className="dp-tab-badge" title="Video visit">
                <span className="material-symbols-outlined" style={{ fontSize: 14 }}>
                  videocam
                </span>
              </span>
            )}
          </button>
        ))}
      </nav>

      {transcriptApplyQueued && (
        <div className="dp-consult-prep-transcript-queued" role="status">
          <span className="material-symbols-outlined">check_circle</span>
          Transcript suggestions will apply to the consultation form when you start.
        </div>
      )}

      <div className="dp-consult-prep-tab-panel">
        {tab === "summary" && (
          <ConsultationVisitSummaries
            appointmentId={appointmentId}
            preVisit={children}
            autoAnalyzeEnabled
            layout="prep"
            onTranscriptAnalyze={onTranscriptAnalyze}
            onApplyTranscriptToForm={onApplyTranscriptToForm}
            applyLabel="Apply when consultation starts"
          />
        )}
        {tab === "chats" && (
          <PreVisitChatsTab patientId={patientId} patientName={patientName} />
        )}
        {tab === "transcript" && (
          <PreVisitTranscriptTab appointmentId={appointmentId} isVideo={isVideo} />
        )}
      </div>

      <div className="dp-consult-prep-cta">
        <p>
          {reportVisit
            ? "Review the uploaded report, chat history, and transcript, then start documenting your discussion."
            : "Review pre-visit data, AI chats, and transcript, then start — the form will pre-fill from triage with one-click AI assist."}
        </p>
        <button
          type="button"
          className="dp-btn dp-btn--primary"
          disabled={!canStart || saving}
          onClick={onStartConsultation}
        >
          <span className="material-symbols-outlined">play_circle</span>
          {saving ? "Starting…" : reportVisit ? "Start report discussion" : "Start consultation"}
        </button>
      </div>
    </section>
  );
}
