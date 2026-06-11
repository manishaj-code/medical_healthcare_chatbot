import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, apiUpload, setTokens } from "../api/client";
import ChatFileAttachment, { ChatAttachment } from "./ChatFileAttachment";
import { ChatBookingUI, ChatUiPayload, formatChatText } from "./ChatBookingUI";
import { CHAT_QUICK_ACTIONS, resolveDisplayText } from "../utils/chatTokens";
import { ensureGuestSession, resetGuestSession } from "../utils/guestSession";
import {
  finalizeChatMessages,
  shouldHideBookingCardCaption,
  shouldShowInteractiveBookingUi,
} from "../utils/chatUiHelpers";
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
  resume_prompt?: string | null;
  pending_auth_action?: string | null;
  upload_kind?: "symptom" | "report" | null;
}

interface GuestHistoryResponse {
  messages: GuestMessage[];
  awaiting_input?: "email" | "otp" | "upload" | null;
}

const GUEST_WELCOME_TEXT =
  "Hello! I'm MediAI, your AI health assistant. Describe any symptom or concern " +
  "in your own words — I'll listen, ask follow-up questions, and guide you with care.";

function makeGuestWelcomeMessage(): GuestMessage {
  return { role: "assistant", content: GUEST_WELCOME_TEXT };
}

function inputPlaceholder(awaiting: string | null, uploadKind: "symptom" | "report" | null): string {
  if (awaiting === "email") return "Enter your email address...";
  if (awaiting === "otp") return "Enter 6-digit verification code...";
  if (awaiting === "upload" && uploadKind === "symptom") {
    return "Choose a symptom photo to upload...";
  }
  if (awaiting === "upload") return "Choose a file to upload...";
  return "Symptoms or health question...";
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function GuestChatWidget({ open, onOpenChange }: Props) {
  const navigate = useNavigate();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<GuestMessage[]>(() => [makeGuestWelcomeMessage()]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [initError, setInitError] = useState("");
  const [sessionConnecting, setSessionConnecting] = useState(true);
  const [awaitingInput, setAwaitingInput] = useState<"email" | "otp" | "upload" | null>(null);
  const [uploadKind, setUploadKind] = useState<"symptom" | "report" | null>(null);
  const [devOtpHint, setDevOtpHint] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [redirecting, setRedirecting] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const widgetRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const pendingUploadOpen = useRef(false);

  const bootstrapGuestSession = useCallback(async () => {
    setSessionConnecting(true);
    setInitError("");
    try {
      const id = await ensureGuestSession();
      setSessionId(id);
    } catch (err) {
      const message =
        err instanceof Error && err.message
          ? err.message
          : "Could not start chat. Make sure the backend API is running, then try again.";
      setInitError(message);
      setSessionId(null);
    } finally {
      setSessionConnecting(false);
    }
  }, []);

  useEffect(() => {
    void bootstrapGuestSession();
  }, [bootstrapGuestSession]);

  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    api<GuestHistoryResponse>(`/api/v1/guest/chat/history?session_id=${encodeURIComponent(sessionId)}`)
      .then((data) => {
        if (!active) return;
        if (data.messages?.length) {
          setMessages(
            finalizeChatMessages(
              data.messages.map((m) =>
                m.role === "user" ? { ...m, content: resolveDisplayText(m.content) } : m
              )
            )
          );
        } else {
          setMessages([makeGuestWelcomeMessage()]);
        }
        if (data.awaiting_input) setAwaitingInput(data.awaiting_input);
        if (data.awaiting_input === "upload") {
          setUploadKind(
            (data as GuestHistoryResponse & { upload_kind?: string }).upload_kind === "symptom"
              ? "symptom"
              : "report"
          );
        }
      })
      .catch(() => {
        if (!active) return;
        void resetGuestSession().then((freshId) => {
          if (active) setSessionId(freshId);
        });
      });
    return () => {
      active = false;
    };
  }, [sessionId]);

  useEffect(() => {
    if (open) bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, open, devOtpHint]);

  useEffect(() => {
    if (!pendingUploadOpen.current || loading || !sessionId || awaitingInput !== "upload") return;
    pendingUploadOpen.current = false;
    const timer = window.setTimeout(() => fileRef.current?.click(), 120);
    return () => window.clearTimeout(timer);
  }, [awaitingInput, uploadKind, loading, sessionId]);

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
      if (res.pending_auth_action) {
        sessionStorage.setItem("post_signup_pending_action", res.pending_auth_action);
      }
      setAwaitingInput(null);
      setDevOtpHint(null);
      setRedirecting(true);
      setTimeout(() => {
        navigate("/chat", {
          replace: true,
          state: {
            conversationId: res.conversation_id,
            fromGuestBooking: true,
          },
        });
      }, 2200);
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
      const shown = displayText ?? resolveDisplayText(trimmed);
      setMessages((m) => [...m, { role: "user", content: shown }]);
      setLoading(true);
      let sid = sessionId;
      try {
        let res: GuestChatResponse;
        try {
          res = await postGuestMessage(sid, trimmed);
        } catch (firstErr) {
          const firstMsg = firstErr instanceof Error ? firstErr.message : "";
          const sessionLost = /expired|session/i.test(firstMsg);
          if (sessionLost) {
            sid = await resetGuestSession();
            setSessionId(sid);
            res = await postGuestMessage(sid, trimmed);
          } else {
            throw firstErr;
          }
        }
        if (!res?.reply) {
          throw new Error("Empty response from assistant");
        }
        setAwaitingInput(res.awaiting_input ?? null);
        setUploadKind(res.upload_kind ?? null);
        if (res.awaiting_input === "upload") pendingUploadOpen.current = true;
        setDevOtpHint(res.dev_otp ?? null);
        setMessages((m) =>
          finalizeChatMessages([
            ...m,
            { role: "assistant", content: res.reply, ui: res.ui },
          ])
        );
        if (res.auth_complete) {
          handleAuthComplete(res);
        }
      } catch {
        setMessages((m) =>
          finalizeChatMessages([
            ...m,
            {
              role: "assistant",
              content:
                "Sorry, something went wrong. Please refresh the page and try again — your session may have expired after a restart.",
            },
          ])
        );
      }
      setLoading(false);
    },
    [sessionId, loading, handleAuthComplete, postGuestMessage]
  );

  const uploadFile = useCallback(
    async (file: File, kind: "symptom" | "report") => {
      if (!sessionId || loading) return;
      setMessages((m) => [
        ...m,
        {
          role: "user",
          content: "",
          attachment: {
            type: kind === "symptom" ? "image" : "report",
            filename: file.name,
            size_bytes: file.size,
          },
        },
      ]);
      setLoading(true);
      const endpoint =
        kind === "symptom" ? "/api/v1/guest/symptom-image" : "/api/v1/guest/report-upload";
      try {
        const form = new FormData();
        form.append("session_id", sessionId);
        form.append("file", file);
        const res = await apiUpload<GuestChatResponse>(endpoint, form);
        setAwaitingInput(res.awaiting_input ?? null);
        setUploadKind(res.upload_kind ?? null);
        setMessages((m) =>
          finalizeChatMessages([
            ...m,
            { role: "assistant", content: res.reply, ui: res.ui },
          ])
        );
      } catch (err) {
        const detail = err instanceof Error ? err.message : "Upload failed.";
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            content: `Sorry, ${kind === "symptom" ? "symptom photo" : "report"} upload failed. ${detail}`,
          },
        ]);
      }
      setLoading(false);
    },
    [sessionId, loading]
  );

  const uploadReport = useCallback(
    (file: File) => uploadFile(file, "report"),
    [uploadFile]
  );

  const uploadSymptomImage = useCallback(
    (file: File) => uploadFile(file, "symptom"),
    [uploadFile]
  );

  const onPick = (message: string) => {
    void sendText(message, resolveDisplayText(message));
  };

  const handleQuickAction = (action: (typeof CHAT_QUICK_ACTIONS)[number]) => {
    void sendText(action.token, action.label);
  };

  const startOver = async () => {
    if (loading) return;
    setLoading(true);
    setInitError("");
    try {
      const freshId = await resetGuestSession();
      setSessionId(freshId);
      setMessages([makeGuestWelcomeMessage()]);
      setAwaitingInput(null);
      setUploadKind(null);
      setDevOtpHint(null);
      setInput("");
    } catch {
      setInitError("Could not start a new chat. Please refresh the page.");
    } finally {
      setLoading(false);
    }
  };

  const lastAssistantIdx = messages.reduce(
    (last, msg, idx) => (msg.role === "assistant" ? idx : last),
    -1
  );

  const hasUserMessages = messages.some((m) => m.role === "user");
  const showQuickActions = !hasUserMessages && !initError;

  return (
    <div
      ref={widgetRef}
      className={`aura-chat-widget${open ? " aura-chat-widget--open" : ""}${expanded ? " aura-chat-widget--expanded" : ""}`}
    >
      {/* Redirect loading overlay */}
      {redirecting && (
        <div className="aura-redirect-overlay">
          <div className="aura-redirect-card">
            <div className="aura-redirect-spinner">
              <div className="aura-redirect-spinner-ring" />
              <span className="aura-redirect-spinner-icon">🏥</span>
            </div>
            <h4 className="aura-redirect-title">Redirecting to AI Consultation Portal</h4>
            <p className="aura-redirect-msg">
              Please wait while we securely prepare your session…
            </p>
            <div className="aura-redirect-progress">
              <div className="aura-redirect-progress-bar" />
            </div>
            <p className="aura-redirect-sub">Your booking has been confirmed. Taking you there now.</p>
          </div>
        </div>
      )}
      <div
        className={`aura-chat-window${open ? " aura-chat-window--open" : ""}${expanded ? " aura-chat-window--expanded" : ""}`}
      >
        <header className="aura-chat-header">
          <div className="aura-chat-header-left">
            <div className="aura-chat-header-icon">
              <span className="material-symbols-outlined">clinical_notes</span>
            </div>
            <div>
              <h4>MediAI Assistant</h4>
              <span className="aura-chat-status">
                <span className="aura-chat-status-dot" />
                Active Now
              </span>
            </div>
          </div>
          <div className="aura-chat-header-actions">
            {hasUserMessages && (
              <button
                type="button"
                className="aura-chat-close"
                onClick={() => void startOver()}
                disabled={loading}
                aria-label="Start over"
                title="Start a new conversation"
              >
                <span className="material-symbols-outlined">restart_alt</span>
              </button>
            )}
            <button type="button" className="aura-chat-close" onClick={() => { onOpenChange(false); setExpanded(false); }} aria-label="Close">
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>
        </header>

        <div
          className="aura-chat-messages"
          onClick={() => { if (open) setExpanded(true); }}
        >
          {initError && <p className="aura-chat-error">{initError}</p>}

          {messages.map((m, i) => {
            const isUser = m.role === "user";
            const showUi =
              m.role === "assistant" && shouldShowInteractiveBookingUi(m.ui, i, lastAssistantIdx);
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
                    <p>{resolveDisplayText(m.content)}</p>
                  ) : showUi ? (
                    <>
                      {m.content.trim() && !shouldHideBookingCardCaption(m.ui) && (
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

          {showQuickActions && (
            <div className="aura-chat-quick-actions">
              {CHAT_QUICK_ACTIONS.map((action) => (
                <button
                  key={action.label}
                  type="button"
                  disabled={loading || sessionConnecting || !sessionId}
                  onClick={() => handleQuickAction(action)}
                >
                  {action.label}
                </button>
              ))}
            </div>
          )}

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
            accept={uploadKind === "symptom" ? "image/*" : REPORT_UPLOAD_ACCEPT}
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (!file) return;
              if (uploadKind === "symptom" || file.type.startsWith("image/")) {
                void uploadSymptomImage(file);
              } else {
                void uploadReport(file);
              }
            }}
          />
          <div className="aura-chat-input-wrap">
            <button
              type="button"
              className="aura-chat-attach"
              disabled={loading || sessionConnecting || !sessionId}
              onClick={() => fileRef.current?.click()}
              aria-label={uploadKind === "symptom" ? "Upload symptom photo" : "Upload medical report"}
              title={uploadKind === "symptom" ? "Upload symptom photo" : "Upload medical report"}
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
              placeholder={
                sessionConnecting
                  ? "Connecting..."
                  : initError
                    ? "Chat unavailable — use Retry below"
                    : inputPlaceholder(awaitingInput, uploadKind)
              }
              disabled={loading || sessionConnecting || !sessionId}
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
          {initError && (
            <div className="aura-chat-session-error" role="alert">
              <p>{initError}</p>
              <button type="button" onClick={() => void bootstrapGuestSession()}>
                Retry connection
              </button>
            </div>
          )}
          <p className="aura-chat-disclaimer">
            AI guidance should not replace professional medical advice.
            {" · "}
            <Link to="/login">Sign in</Link>
          </p>
        </footer>
      </div>

      {!open && (
        <button
          type="button"
          className="aura-chat-fab"
          onClick={() => {
            onOpenChange(true);
            setExpanded(true);
          }}
          aria-label="Open MediAI consultation"
        >
          <span className="material-symbols-outlined">smart_toy</span>
        </button>
      )}
    </div>
  );
}
