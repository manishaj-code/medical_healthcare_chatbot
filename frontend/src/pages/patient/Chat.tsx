import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api, apiUpload, clearTokens } from "../../api/client";
import { ChatBookingUI, ChatUiPayload, formatChatText } from "../../components/ChatBookingUI";
import ChatFileAttachment, {
  ChatAttachment,
  parseLegacyUploadAttachment,
  userMessageCaption,
} from "../../components/ChatFileAttachment";
import ChatReportFollowUp from "../../components/ChatReportFollowUp";
import {
  CHAT_LIST_TITLE,
  Conversation,
  dateKey,
  dedupeConversationsByDate,
  ensureTodayConversation,
  fetchConversations,
  formatChatDateLabel,
} from "../../utils/chatConversations";
import { resolveBookingUi } from "../../utils/chatUiHelpers";
import {
  inferSpecialtyFromSymptoms,
  parseSpecialtyFromText,
  saveHistoryRecommendation,
} from "../../utils/recommendedSpecialty";
import { REPORT_UPLOAD_ACCEPT } from "../../utils/reportUpload";
import {
  detectSymptomsFromMessages,
  extractSymptomLabelsFromMessage,
} from "../../utils/symptomDetection";

interface Message {
  id?: string;
  role: string;
  content: string;
  ui?: ChatUiPayload | null;
  attachment?: ChatAttachment | null;
  reportAck?: boolean;
  created_at?: string;
}

interface ApiMessage {
  id?: string;
  role: string;
  content: string;
  agent_name?: string | null;
  ui?: ChatUiPayload | null;
  attachment?: ChatAttachment | null;
  report_ack?: boolean;
  created_at?: string;
}

function displayUserContent(content: string): string {
  const lines = content
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);
  const deduped: string[] = [];
  for (const line of lines) {
    const prev = deduped[deduped.length - 1];
    if (!prev || prev.toLowerCase() !== line.toLowerCase()) {
      deduped.push(line);
    }
  }
  if (deduped.length <= 1) return deduped[0] ?? content.trim();
  return deduped.join("\n");
}

function normalizeMessages(messages: Message[]): Message[] {
  // API returns chronological order; when timestamps tie, keep that order (not UUID order).
  const sorted = messages
    .map((msg, index) => ({ msg, index }))
    .sort((a, b) => {
      const ta = a.msg.created_at ? Date.parse(a.msg.created_at) : 0;
      const tb = b.msg.created_at ? Date.parse(b.msg.created_at) : 0;
      if (ta !== tb) return ta - tb;
      return a.index - b.index;
    })
    .map(({ msg }) => msg);

  const deduped: Message[] = [];
  for (const msg of sorted) {
    const content = msg.role === "user" ? displayUserContent(msg.content) : msg.content;
    const normalized = { ...msg, content };
    const prev = deduped[deduped.length - 1];
    if (
      prev &&
      normalized.role === "user" &&
      prev.role === "user" &&
      !normalized.attachment &&
      !prev.attachment &&
      normalized.content.trim().toLowerCase() === prev.content.trim().toLowerCase()
    ) {
      continue;
    }
    deduped.push(normalized);
  }
  return deduped;
}

const SYMPTOM_START_OPTIONS = [
  { label: "Headache", message: "Headache" },
  { label: "Fever", message: "Fever" },
  { label: "Cough", message: "Cough" },
  { label: "Body pain", message: "Body pain" },
  { label: "Nausea", message: "Nausea" },
  { label: "Sore throat", message: "Sore throat" },
  { label: "Fatigue", message: "Fatigue" },
  { label: "Book appointment", message: "I'd like to book an appointment with a doctor." },
];

function normalizeRole(role: string): string {
  return String(role).toLowerCase() === "user" ? "user" : "assistant";
}

function enrichApiMessage(m: ApiMessage): Omit<Message, "ui"> & { ui?: ChatUiPayload | null } {
  const attachment = m.attachment ?? parseLegacyUploadAttachment(m.content);
  const role = normalizeRole(m.role);
  return {
    id: m.id,
    role,
    content: role === "user" ? displayUserContent(m.content) : m.content,
    attachment,
    reportAck: !!m.report_ack,
    created_at: m.created_at,
    ui: undefined,
  };
}

function buildChatSidebar(conversations: Conversation[]) {
  return dedupeConversationsByDate(conversations).map((conv) => ({
    id: conv.id,
    dateKey: dateKey(conv.created_at),
    dateLabel: formatChatDateLabel(conv.created_at),
  }));
}

function formatMsgTime(iso?: string): string {
  const d = iso ? new Date(iso) : new Date();
  const today = new Date();
  const isToday =
    d.getDate() === today.getDate() &&
    d.getMonth() === today.getMonth() &&
    d.getFullYear() === today.getFullYear();
  const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
  return isToday ? `Today ${time}` : `${d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })} ${time}`;
}

function userInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (parts[0]?.[0] ?? "P").toUpperCase();
}

function consultationInsights(messages: Message[], emergency: boolean) {
  const userCount = messages.filter((m) => m.role === "user").length;
  const symptoms = detectSymptomsFromMessages(messages);

  let percent = 30;
  let phase = "Intake Phase";
  if (userCount >= 1) {
    percent = 45;
    phase = "Analysis Phase";
  }
  if (userCount >= 2 || symptoms.length >= 1) {
    percent = 65;
    phase = "Analysis Phase";
  }
  if (userCount >= 3 || symptoms.length >= 2) {
    percent = 80;
    phase = "Correlation Phase";
  }
  if (messages.some((m) => m.ui)) percent = 95;

  const steps = [
    { label: "History Review", done: true },
    { label: "Initial Inquiry", done: userCount >= 1 },
    { label: "Symptom Correlation", done: userCount >= 2 || symptoms.length > 0 },
  ];

  const risk = emergency
    ? {
        level: "High",
        title: "Urgent Attention",
        note: "Seek immediate medical care or emergency services.",
        quote: "Critical indicators detected. Do not delay professional evaluation.",
      }
    : symptoms.length >= 2
      ? {
          level: "Moderate",
          title: "Monitor Closely",
          note: "Multiple symptoms reported — follow up if symptoms persist.",
          quote: "Patterns suggest further evaluation may be helpful. Continue monitoring and stay hydrated.",
        }
      : {
          level: "Low",
          title: "Stable Condition",
          note: "No immediate urgent indicators.",
          quote: "Symptoms may align with tension headache or early viral infection. Continue monitoring temperature.",
        };

  return { percent, phase, steps, symptoms, risk };
}

function ConsultActionChips({
  actions,
  disabled,
  onPick,
}: {
  actions: { label: string; message: string }[];
  disabled?: boolean;
  onPick: (message: string) => void;
}) {
  return (
    <div className="consult-action-chips">
      {actions.map((action) => (
        <button
          key={action.label}
          type="button"
          className="consult-action-chip"
          disabled={disabled}
          onClick={() => onPick(action.message)}
        >
          {action.label}
        </button>
      ))}
    </div>
  );
}

export default function PatientChat() {
  const location = useLocation();
  const navigate = useNavigate();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [emergency, setEmergency] = useState(false);
  const [loading, setLoading] = useState(false);
  const [initError, setInitError] = useState("");
  const [initializing, setInitializing] = useState(true);
  const bottom = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const pendingPromptRef = useRef<string | null>(null);
  const lastSendRef = useRef<{ signature: string; at: number } | null>(null);
  const patientName = localStorage.getItem("user_name") || "Patient";

  const insights = consultationInsights(messages, emergency);
  const sidebarItems = buildChatSidebar(conversations);

  const hydrateMessages = async (history: ApiMessage[]) => {
    const enriched = await Promise.all(
      history.map(async (m) => {
        const base = enrichApiMessage(m);
        return {
          ...base,
          ui: await resolveBookingUi(m.ui, m.agent_name ?? undefined, m.content),
        };
      })
    );
    return normalizeMessages(enriched);
  };

  const refreshMessages = async (convId: string) => {
    const history = await api<ApiMessage[]>(`/api/v1/chat/conversations/${convId}/messages`);
    setMessages(await hydrateMessages(history));
  };

  const loadConversationMessages = async (convId: string, list: Conversation[]) => {
    setConversationId(convId);
    await refreshMessages(convId);
    const active = list.find((c) => c.id === convId);
    setEmergency(!!active?.emergency_flag);
  };

  const loadConversations = useCallback(async (selectId?: string) => {
    const conv = selectId ? { id: selectId } : await ensureTodayConversation();
    const list = await fetchConversations();
    const convId = selectId ?? conv.id;
    setConversations(list);
    await loadConversationMessages(convId, list);
  }, []);

  useEffect(() => {
    let active = true;
    const initChat = async () => {
      setInitError("");
      setInitializing(true);
      const navState = location.state as { conversationId?: string; promptMessage?: string } | null;
      if (navState?.promptMessage) {
        pendingPromptRef.current = navState.promptMessage;
        navigate(location.pathname, { replace: true, state: navState.conversationId ? { conversationId: navState.conversationId } : {} });
      }
      const resumeId =
        navState?.conversationId ?? sessionStorage.getItem("post_signup_conversation_id") ?? undefined;
      if (resumeId) sessionStorage.removeItem("post_signup_conversation_id");
      try {
        await loadConversations(resumeId);
      } catch (err: unknown) {
        if (!active) return;
        const msg = err instanceof Error ? err.message : "Could not start chat";
        setInitError(msg);
        if (msg.toLowerCase().includes("session") || msg.toLowerCase().includes("token")) {
          clearTokens();
        }
      } finally {
        if (active) setInitializing(false);
      }
    };
    void initChat();
    return () => {
      active = false;
    };
  }, [loadConversations, location.state, location.pathname, navigate]);

  useEffect(() => {
    const prompt = pendingPromptRef.current;
    if (!prompt || initializing || loading || !conversationId) return;
    pendingPromptRef.current = null;
    void sendText(prompt);
  }, [initializing, loading, conversationId]);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (!loading && !initializing && conversationId) {
      textareaRef.current?.focus();
    }
  }, [loading, initializing, conversationId]);

  const resizeTextarea = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
  };

  useEffect(() => {
    resizeTextarea();
  }, [input]);

  const selectConversation = async (convId: string) => {
    if (convId === conversationId || loading) return;
    setConversationId(convId);
    setLoading(true);
    try {
      await refreshMessages(convId);
      const conv = conversations.find((c) => c.id === convId);
      setEmergency(!!conv?.emergency_flag);
    } catch {
      setInitError("Could not load conversation.");
    }
    setLoading(false);
  };

  const sendText = async (
    text: string,
    reportId?: string,
    attachment?: ChatAttachment,
    options?: { fromUpload?: boolean; fromReportAction?: boolean; displayText?: string }
  ) => {
    if (!text.trim() || !conversationId) return;
    if (!options?.fromUpload && !options?.fromReportAction && loading) return;

    const trimmed = text.trim();
    const signature = `${conversationId}:${trimmed}:${reportId ?? ""}`;
    const last = lastSendRef.current;
    if (last && last.signature === signature && Date.now() - last.at < 2500) return;
    lastSendRef.current = { signature, at: Date.now() };

    setLoading(true);
    try {
      const body: {
        message: string;
        report_id?: string;
        attachment_filename?: string;
        attachment_size_bytes?: number;
      } = { message: trimmed };
      if (reportId) body.report_id = reportId;
      if (attachment?.filename) body.attachment_filename = attachment.filename;
      if (attachment?.size_bytes != null) body.attachment_size_bytes = attachment.size_bytes;
      const res = await api<{ reply: string; emergency: boolean; agent: string; ui?: ChatUiPayload | null }>(
        `/api/v1/chat/conversations/${conversationId}/messages`,
        { method: "POST", body: JSON.stringify(body) }
      );
      setEmergency(res.emergency);
      await refreshMessages(conversationId);
      const userSymptoms = extractSymptomLabelsFromMessage(trimmed);
      if (userSymptoms.length) {
        const recommended = parseSpecialtyFromText(res.reply);
        const specialty = recommended || inferSpecialtyFromSymptoms(userSymptoms);
        saveHistoryRecommendation({ specialty, symptoms: userSymptoms });
      }
    } catch {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: "Sorry, something went wrong. Please try again.", created_at: new Date().toISOString() },
      ]);
    }
    setLoading(false);
  };

  const send = async () => {
    if (!input.trim()) return;
    const text = input.trim();
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    await sendText(text);
  };

  const uploadReport = async (file: File) => {
    if (!conversationId || loading) return;
    setLoading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const uploaded = await apiUpload<{ report_id: string; id: string }>("/api/v1/reports/upload", form);
      const reportId = uploaded.report_id || uploaded.id;
      await api(`/api/v1/chat/conversations/${conversationId}/report-upload`, {
        method: "POST",
        body: JSON.stringify({
          report_id: reportId,
          filename: file.name,
          size_bytes: file.size,
        }),
      });
      await refreshMessages(conversationId);
      setLoading(false);
    } catch {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: "Sorry, report upload failed. Please try again.", created_at: new Date().toISOString() },
      ]);
      setLoading(false);
    }
  };

  const startNewChat = async () => {
    if (loading || initializing) return;
    setLoading(true);
    try {
      const conv = await ensureTodayConversation();
      const list = await fetchConversations();
      setConversations(list);
      await loadConversationMessages(conv.id, list);
    } catch {
      setInitError("Could not start a new chat. Please try again.");
    }
    setLoading(false);
  };

  const exportChat = () => {
    const lines = messages.map((m) => {
      const who = m.role === "user" ? "You" : "MediAI";
      const time = m.created_at ? formatMsgTime(m.created_at) : "";
      return `[${time}] ${who}:\n${m.content}`;
    });
    const blob = new Blob([lines.join("\n\n")], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `mediai-consultation-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const lastAssistantIdx = messages.reduce(
    (last, msg, idx) => (msg.role === "assistant" ? idx : last),
    -1
  );

  const REPORT_ACK_SNIPPET = "I've received the medical documents";

  const shouldShowReportFollowUp = (index: number) => {
    const msg = messages[index];
    if (msg.role !== "assistant" || !msg.reportAck) return false;
    if (!msg.content.includes(REPORT_ACK_SNIPPET)) return false;
    return !messages.slice(index + 1).some((m) => m.role === "user");
  };

  const reportFollowUpAttachment = (index: number): ChatAttachment | null => {
    const msg = messages[index];
    const prev = messages[index - 1];
    if (prev?.attachment) return prev.attachment;
    if (msg.attachment) return msg.attachment;
    return null;
  };

  return (
    <div className="consult-shell">
      <header className="consult-topbar">
        <div className="consult-topbar-left">
          <h2>Consultation</h2>
          <span className="consult-ai-badge">
            <span className="consult-ai-pulse" />
            AI ACTIVE
          </span>
          {sidebarItems.length > 1 && (
            <select
              className="consult-history-select"
              value={conversationId ?? ""}
              onChange={(e) => selectConversation(e.target.value)}
              disabled={loading || initializing}
              aria-label="Chat history"
            >
              {sidebarItems.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.dateLabel} — {CHAT_LIST_TITLE}
                </option>
              ))}
            </select>
          )}
        </div>
        <div className="consult-topbar-right">
          <div className="consult-search">
            <span className="material-symbols-outlined">search</span>
            <input type="search" placeholder="Search health data..." aria-label="Search health data" />
          </div>
          <button type="button" className="consult-icon-btn" title="Notifications">
            <span className="material-symbols-outlined">notifications</span>
          </button>
          <button type="button" className="consult-icon-btn" title="Help">
            <span className="material-symbols-outlined">help_outline</span>
          </button>
          <div className="consult-topbar-avatar">{userInitials(patientName)}</div>
        </div>
      </header>

      <section className="consult-split">
        <div className="consult-chat">
          {emergency && (
            <div className="consult-emergency">
              <span className="material-symbols-outlined">emergency</span>
              Emergency detected — please seek immediate medical care or call emergency services.
            </div>
          )}
          {initError && (
            <div className="consult-emergency consult-emergency--error">
              {initError}. Please <a href="/login">log in again</a>.
            </div>
          )}

          <div className="consult-messages consult-scroll">
            {initializing && (
              <p className="consult-empty">Loading your consultation...</p>
            )}
            {!initializing && messages.length === 0 && (
              <div className="consult-welcome-msg">
                <div className="consult-msg consult-msg--ai">
                  <div className="consult-avatar consult-avatar--ai">
                    <span className="material-symbols-outlined">smart_toy</span>
                  </div>
                  <div className="consult-msg-body">
                    <div className="consult-bubble consult-bubble--ai">
                      <p>
                        Hello {patientName.split(" ")[0]}, I&apos;m your MediAI Assistant. How are you feeling today?
                        Tap a symptom below to get started — no typing needed.
                      </p>
                      <ConsultActionChips
                        actions={SYMPTOM_START_OPTIONS}
                        disabled={loading || !conversationId}
                        onPick={sendText}
                      />
                    </div>
                    <span className="consult-time">{formatMsgTime()}</span>
                  </div>
                </div>
              </div>
            )}

            {messages.map((m, i) => {
              const isUser = m.role === "user";
              const prev = messages[i - 1];
              const showInteractiveUi = m.role === "assistant" && m.ui && i === lastAssistantIdx;
              const showReportFollowUp = shouldShowReportFollowUp(i);
              const userCaption = isUser ? userMessageCaption(m.content, !!m.attachment) : null;
              const userText = isUser ? (m.attachment ? userCaption : displayUserContent(m.content)) : null;
              return (
                <div key={m.id ?? `${m.role}-${m.created_at ?? i}`} className={`consult-msg ${isUser ? "consult-msg--user" : "consult-msg--ai"}`}>
                  <div className={`consult-avatar ${isUser ? "consult-avatar--user" : "consult-avatar--ai"}`}>
                    <span className="material-symbols-outlined">{isUser ? "person" : "smart_toy"}</span>
                  </div>
                  <div className="consult-msg-body">
                    <div className={`consult-bubble ${isUser ? "consult-bubble--user" : "consult-bubble--ai"}${showInteractiveUi ? " consult-bubble--booking" : ""}${m.attachment ? " consult-bubble--with-file" : ""}${showReportFollowUp ? " consult-bubble--with-report-actions" : ""}`}>
                      {isUser && m.attachment && (
                        <ChatFileAttachment attachment={m.attachment} variant="upload" />
                      )}
                      {isUser && userText && <p>{userText}</p>}
                      {m.role === "assistant" && !showInteractiveUi && (
                        <>
                          <div className="consult-msg-text">{formatChatText(m.content)}</div>
                          {showReportFollowUp && reportFollowUpAttachment(i) && (
                            <ChatReportFollowUp
                              attachment={reportFollowUpAttachment(i)!}
                              disabled={loading || !conversationId}
                              onPick={(message, display) => {
                                const att = reportFollowUpAttachment(i)!;
                                void sendText(message, att.report_id, undefined, {
                                  fromReportAction: true,
                                  displayText: display,
                                });
                              }}
                            />
                          )}
                        </>
                      )}
                      {showInteractiveUi && (
                        <div className="consult-booking-wrap">
                          {m.content.trim() && (
                            <div className="consult-msg-text consult-msg-text--compact">{formatChatText(m.content)}</div>
                          )}
                          <ChatBookingUI ui={m.ui!} disabled={loading} onPick={sendText} />
                        </div>
                      )}
                    </div>
                    <span className="consult-time">{formatMsgTime(m.created_at)}</span>
                  </div>
                </div>
              );
            })}

            {loading && (
              <div className="consult-msg consult-msg--ai consult-msg--typing">
                <div className="consult-avatar consult-avatar--ai">
                  <span className="material-symbols-outlined consult-spin">sync</span>
                </div>
                <div className="consult-typing-dots">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            )}
            <div ref={bottom} />
          </div>

          <div className="consult-composer-wrap">
            <div className="consult-composer-row">
              <button
                type="button"
                className="consult-refresh-btn"
                title="Refresh consultation"
                onClick={() => void startNewChat()}
                disabled={loading || initializing}
              >
                <span className="material-symbols-outlined">restart_alt</span>
              </button>
              <div className="consult-composer">
                <input
                  ref={fileRef}
                  type="file"
                  accept={REPORT_UPLOAD_ACCEPT}
                  hidden
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) uploadReport(f);
                    e.target.value = "";
                  }}
                />
                <button
                  type="button"
                  className="consult-attach-btn"
                  title="Attach medical report (PDF, image, Word, Excel, CSV, text)"
                  onClick={() => fileRef.current?.click()}
                  disabled={loading || !conversationId || initializing}
                >
                  <span className="material-symbols-outlined">attach_file</span>
                </button>
                <textarea
                  ref={textareaRef}
                  rows={1}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void send();
                    }
                  }}
                  placeholder="Type your symptoms or health questions..."
                  disabled={loading || !conversationId || initializing}
                />
                <button
                  type="button"
                  className="consult-send-btn"
                  onClick={() => void send()}
                  disabled={loading || !conversationId || initializing || !input.trim()}
                  aria-label="Send message"
                >
                  <span className="material-symbols-outlined">send</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        <aside className="consult-insights consult-scroll">
          <div className="consult-card">
            <h3>Consultation Progress</h3>
            <div className="consult-progress-meta">
              <span className="consult-phase-badge">{insights.phase}</span>
              <span className="consult-progress-pct">{insights.percent}%</span>
            </div>
            <div className="consult-progress-bar">
              <div className="consult-progress-fill" style={{ width: `${insights.percent}%` }} />
            </div>
            <ul className="consult-steps">
              {insights.steps.map((step) => (
                <li key={step.label} className={step.done ? "done" : ""}>
                  <span className="material-symbols-outlined">
                    {step.done ? "check_circle" : "radio_button_unchecked"}
                  </span>
                  {step.label}
                </li>
              ))}
            </ul>
          </div>

          <div className="consult-card">
            <h3>Detected Symptoms</h3>
            {insights.symptoms.length > 0 && (
              <div className="consult-symptom-tags">
                {insights.symptoms.map((s) => (
                  <span key={s.label} className="consult-symptom-tag">
                    <span className="material-symbols-outlined">{s.icon}</span>
                    {s.label}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="consult-card consult-risk-card">
            <span className="consult-risk-deco material-symbols-outlined">analytics</span>
            <h3>Risk Assessment</h3>
            <div className="consult-risk-row">
              <div className={`consult-risk-ring ${emergency ? "urgent" : ""}`}>
                <span>{insights.risk.level}</span>
              </div>
              <div>
                <p className="consult-risk-title">{insights.risk.title}</p>
                <p className="consult-risk-note">{insights.risk.note}</p>
              </div>
            </div>
            <div className="consult-risk-quote">
              <p>&ldquo;{insights.risk.quote}&rdquo;</p>
            </div>
          </div>

          <div className="consult-quick-grid">
            <Link to="/appointments" className="consult-quick-btn">
              <span className="material-symbols-outlined">medication</span>
              <span>My Meds</span>
            </Link>
            <Link to="/doctors" className="consult-quick-btn">
              <span className="material-symbols-outlined">calendar_month</span>
              <span>Book Dr.</span>
            </Link>
            <Link to="/reports" className="consult-quick-btn">
              <span className="material-symbols-outlined">lab_panel</span>
              <span>All Reports</span>
            </Link>
            <button type="button" className="consult-quick-btn" onClick={exportChat} disabled={messages.length === 0}>
              <span className="material-symbols-outlined">share</span>
              <span>Export</span>
            </button>
          </div>

        </aside>
      </section>
    </div>
  );
}
