import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, apiUpload, setTokens } from "../api/client";
import ChatFileAttachment, { ChatAttachment } from "./ChatFileAttachment";
import { ChatBookingUI, ChatUiPayload, formatChatText } from "./ChatBookingUI";
import { ensureGuestSession, resetGuestSession } from "../utils/guestSession";
import { REPORT_UPLOAD_ACCEPT } from "../utils/reportUpload";

interface GuestMessage {
  role: "user" | "assistant";
  content: string;
  ui?: ChatUiPayload | null;
  attachment?: ChatAttachment | null;
}

interface GuestChatResponse {
  reply: string;
  emergency: boolean;
  ui?: ChatUiPayload | null;
  awaiting_input?: "email" | "otp" | "upload" | null;
  dev_otp?: string | null;
  auth_complete?: boolean;
  access_token?: string | null;
  refresh_token?: string | null;
  user?: { name: string; role: string } | null;
  conversation_id?: string | null;
}

const START_SYMPTOM_TRIAGE = "[start_symptom_triage]";
const START_FIND_DOCTOR = "[start_find_doctor]";
const START_EXPLAIN_REPORT = "[start_explain_report]";

/** Hidden API tokens → friendly text shown in the chat bubble */
const INTERNAL_TOKEN_LABELS: Record<string, string> = {
  [START_SYMPTOM_TRIAGE]: "Check my symptoms",
  [START_FIND_DOCTOR]: "Find a specialist doctor",
  [START_EXPLAIN_REPORT]: "Explain my medical report",
};

const QUICK_ACTIONS = [
  { label: "Check my symptoms", token: START_SYMPTOM_TRIAGE },
  { label: "Find a specialist doctor", token: START_FIND_DOCTOR },
  { label: "Explain my medical report", token: START_EXPLAIN_REPORT },
];

function inputPlaceholder(awaiting: string | null): string {
  if (awaiting === "email") return "Enter your email address...";
  if (awaiting === "otp") return "Enter 6-digit verification code...";
  if (awaiting === "upload") return "Upload your report with the paperclip...";
  return "Type your health concern...";
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function GuestChatWidget({ open, onOpenChange }: Props) {
  const navigate = useNavigate();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<GuestMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [initError, setInitError] = useState("");
  const [intakeStarted, setIntakeStarted] = useState(false);
  const [awaitingInput, setAwaitingInput] = useState<"email" | "otp" | "upload" | null>(null);
  const [devOtpHint, setDevOtpHint] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const widgetRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    ensureGuestSession()
      .then(setSessionId)
      .catch(() => setInitError("Could not start chat. Please refresh."));
  }, []);

  useEffect(() => {
    if (open) bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, open, devOtpHint]);

  useEffect(() => {
    if (!expanded) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!widgetRef.current?.contains(e.target as Node)) {
        setExpanded(false);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [expanded]);

  const handleAuthComplete = useCallback(
    (res: GuestChatResponse) => {
      if (!res.access_token || !res.refresh_token || !res.user) return;
      setTokens(res.access_token, res.refresh_token);
      localStorage.setItem("user_role", res.user.role);
      localStorage.setItem("user_name", res.user.name);
      localStorage.removeItem("guest_session_id");
      if (res.conversation_id) {
        sessionStorage.setItem("post_signup_conversation_id", res.conversation_id);
      }
      setAwaitingInput(null);
      setDevOtpHint(null);
      setTimeout(() => {
        navigate("/chat", {
          replace: true,
          state: res.conversation_id
            ? { conversationId: res.conversation_id, fromGuestBooking: true }
            : { fromGuestBooking: true },
        });
      }, 800);
    },
    [navigate]
  );

  const postGuestMessage = useCallback(
    async (sid: string, text: string) => {
      return api<GuestChatResponse>("/api/v1/guest/chat/messages", {
        method: "POST",
        body: JSON.stringify({ session_id: sid, message: text }),
      });
    },
    []
  );

  const sendText = useCallback(
    async (text: string, displayText?: string) => {
      if (!text.trim() || !sessionId || loading) return;
      const trimmed = text.trim();
      const shown = displayText ?? INTERNAL_TOKEN_LABELS[trimmed] ?? trimmed;
      setMessages((m) => [...m, { role: "user", content: shown }]);
      setLoading(true);
      let sid = sessionId;
      try {
        let res: GuestChatResponse;
        try {
          res = await postGuestMessage(sid, trimmed);
        } catch (err) {
          const msg = err instanceof Error ? err.message.toLowerCase() : "";
          if (msg.includes("expired") || msg.includes("not found") || msg.includes("404")) {
            sid = await resetGuestSession();
            setSessionId(sid);
            res = await postGuestMessage(sid, trimmed);
          } else {
            throw err;
          }
        }
        setAwaitingInput(res.awaiting_input ?? null);
        setDevOtpHint(res.dev_otp ?? null);
        setMessages((m) => [...m, { role: "assistant", content: res.reply, ui: res.ui }]);
        if (res.auth_complete) {
          handleAuthComplete(res);
        }
      } catch {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: "Sorry, something went wrong. Please try again." },
        ]);
      }
      setLoading(false);
    },
    [sessionId, loading, handleAuthComplete, postGuestMessage]
  );

  const uploadReport = useCallback(
    async (file: File) => {
      if (!sessionId || loading) return;
      setIntakeStarted(true);
      setMessages((m) => [
        ...m,
        {
          role: "user",
          content: "",
          attachment: {
            type: "report",
            filename: file.name,
            size_bytes: file.size,
          },
        },
      ]);
      setLoading(true);
      try {
        const form = new FormData();
        form.append("session_id", sessionId);
        form.append("file", file);
        const res = await apiUpload<GuestChatResponse>("/api/v1/guest/report-upload", form);
        setAwaitingInput(res.awaiting_input ?? null);
        setMessages((m) => [...m, { role: "assistant", content: res.reply, ui: res.ui }]);
      } catch (err) {
        const detail = err instanceof Error ? err.message : "Upload failed.";
        setMessages((m) => [
          ...m,
          { role: "assistant", content: `Sorry, report upload failed. ${detail}` },
        ]);
      }
      setLoading(false);
    },
    [sessionId, loading]
  );

  const onPick = (message: string) => {
    setIntakeStarted(true);
    void sendText(message);
  };

  const handleQuickAction = (action: (typeof QUICK_ACTIONS)[number]) => {
    setIntakeStarted(true);
    void sendText(action.token, action.label);
  };

  const lastAssistantIdx = messages.reduce(
    (last, msg, idx) => (msg.role === "assistant" ? idx : last),
    -1
  );

  const hasUserMessages = messages.some((m) => m.role === "user");
  const showWelcome = !hasUserMessages && !initError && !intakeStarted;

  return (
    <div
      ref={widgetRef}
      className={`aura-chat-widget${expanded ? " aura-chat-widget--expanded" : ""}`}
    >
      <button
        type="button"
        className="aura-chat-fab"
        onClick={() => onOpenChange(!open)}
        aria-label={open ? "Close consultation" : "Open AI consultation"}
      >
        <span className="material-symbols-outlined">smart_toy</span>
      </button>

      <div
        className={`aura-chat-window${open ? " aura-chat-window--open" : ""}${expanded ? " aura-chat-window--expanded" : ""}`}
      >
        <header className="aura-chat-header">
          <div className="aura-chat-header-left">
            <div className="aura-chat-header-icon">
              <span className="material-symbols-outlined">clinical_notes</span>
            </div>
            <div>
              <h4>Aura Assistant</h4>
              <span className="aura-chat-status">
                <span className="aura-chat-status-dot" />
                Active Now
              </span>
            </div>
          </div>
          <button type="button" className="aura-chat-close" onClick={() => onOpenChange(false)} aria-label="Close">
            <span className="material-symbols-outlined">close</span>
          </button>
        </header>

        <div className="aura-chat-messages">
          {initError && <p className="aura-chat-error">{initError}</p>}

          {showWelcome && (
            <div className="aura-chat-msg">
              <div className="aura-chat-avatar">
                <span className="material-symbols-outlined">smart_toy</span>
              </div>
              <div className="aura-chat-bubble aura-chat-bubble--ai">
                <p>
                  Hello! I&apos;m Aura, your MediAI concierge. How can I assist you with your health today?
                </p>
              </div>
            </div>
          )}

          {showWelcome && (
            <div className="aura-chat-quick-actions">
              {QUICK_ACTIONS.map((action) => (
                <button
                  key={action.label}
                  type="button"
                  disabled={loading}
                  onClick={() => handleQuickAction(action)}
                >
                  {action.label}
                </button>
              ))}
            </div>
          )}

          {messages.map((m, i) => {
            const isUser = m.role === "user";
            const showUi = m.role === "assistant" && m.ui && i === lastAssistantIdx;
            return (
              <div key={i} className={`aura-chat-msg${isUser ? " aura-chat-msg--user" : ""}`}>
                {!isUser && (
                  <div className="aura-chat-avatar">
                    <span className="material-symbols-outlined">smart_toy</span>
                  </div>
                )}
                <div
                  className={`aura-chat-bubble${isUser ? " aura-chat-bubble--user" : " aura-chat-bubble--ai"}${m.attachment ? " aura-chat-bubble--with-file" : ""}`}
                >
                  {isUser && m.attachment ? (
                    <ChatFileAttachment attachment={m.attachment} variant="upload" />
                  ) : isUser ? (
                    <p>{m.content}</p>
                  ) : showUi ? (
                    <>
                      {m.content.trim() && (
                        <div className="aura-chat-text">{formatChatText(m.content)}</div>
                      )}
                      <ChatBookingUI ui={m.ui!} disabled={loading} onPick={onPick} />
                    </>
                  ) : (
                    <div className="aura-chat-text">{formatChatText(m.content)}</div>
                  )}
                </div>
              </div>
            );
          })}

          {devOtpHint && (
            <p className="aura-chat-dev-otp">Dev code: <strong>{devOtpHint}</strong></p>
          )}

          {loading && (
            <div className="aura-chat-msg">
              <div className="aura-chat-avatar">
                <span className="material-symbols-outlined aura-spin">sync</span>
              </div>
              <div className="aura-chat-typing">
                <span /><span /><span />
              </div>
            </div>
          )}
          <div ref={bottom} />
        </div>

        <footer className="aura-chat-composer">
          <input
            ref={fileRef}
            type="file"
            accept={REPORT_UPLOAD_ACCEPT}
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) void uploadReport(file);
            }}
          />
          <div className="aura-chat-input-wrap">
            <button
              type="button"
              className="aura-chat-attach"
              disabled={loading || !sessionId}
              onClick={() => fileRef.current?.click()}
              aria-label="Upload medical report"
              title="Upload medical report"
            >
              <span className="material-symbols-outlined">attach_file</span>
            </button>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onFocus={() => setExpanded(true)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  const t = input.trim();
                  setInput("");
                  void sendText(t);
                }
              }}
              placeholder={inputPlaceholder(awaitingInput)}
              disabled={loading || !sessionId}
              type={awaitingInput === "email" ? "email" : awaitingInput === "otp" ? "text" : "text"}
              inputMode={awaitingInput === "otp" ? "numeric" : undefined}
              autoComplete={awaitingInput === "email" ? "email" : awaitingInput === "otp" ? "one-time-code" : undefined}
            />
            <button
              type="button"
              className="aura-chat-send"
              disabled={loading || !input.trim() || !sessionId}
              onClick={() => {
                const t = input.trim();
                setInput("");
                void sendText(t);
              }}
              aria-label="Send"
            >
              <span className="material-symbols-outlined">send</span>
            </button>
          </div>
          <p className="aura-chat-disclaimer">
            AI guidance should not replace professional medical advice.
            {" · "}
            <Link to="/login">Sign in</Link>
          </p>
        </footer>
      </div>
    </div>
  );
}
