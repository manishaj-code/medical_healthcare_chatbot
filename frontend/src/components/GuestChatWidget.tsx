import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ChatBookingUI, ChatUiPayload, formatChatText } from "./ChatBookingUI";
import GuestSignupModal from "./GuestSignupModal";
import { ensureGuestSession } from "../utils/guestSession";

interface GuestMessage {
  role: "user" | "assistant";
  content: string;
  ui?: ChatUiPayload | null;
}

const START_SYMPTOM_TRIAGE = "[start_symptom_triage]";

const QUICK_ACTIONS = [
  { label: "Analyze my symptoms", triage: true as const },
  { label: "Explain my medical report", signup: "advanced" as const },
  { label: "Find a specialist doctor", signup: "booking" as const },
];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function GuestChatWidget({ open, onOpenChange }: Props) {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<GuestMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [initError, setInitError] = useState("");
  const [signupOpen, setSignupOpen] = useState(false);
  const [signupReason, setSignupReason] = useState<string | undefined>();
  const [intakeStarted, setIntakeStarted] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    ensureGuestSession()
      .then(setSessionId)
      .catch(() => setInitError("Could not start chat. Please refresh."));
  }, []);

  useEffect(() => {
    if (open) bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading, open]);

  const promptSignup = useCallback((reason?: string) => {
    setSignupReason(reason);
    setSignupOpen(true);
  }, []);

  const sendText = useCallback(
    async (text: string) => {
      if (!text.trim() || !sessionId || loading) return;
      const trimmed = text.trim();
      setMessages((m) => [...m, { role: "user", content: trimmed }]);
      setLoading(true);
      try {
        const res = await api<{
          reply: string;
          emergency: boolean;
          ui?: ChatUiPayload | null;
          requires_signup?: boolean;
          signup_reason?: string;
        }>("/api/v1/guest/chat/messages", {
          method: "POST",
          body: JSON.stringify({ session_id: sessionId, message: trimmed }),
        });
        if (res.requires_signup) {
          setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
          promptSignup(res.signup_reason);
        } else {
          setMessages((m) => [...m, { role: "assistant", content: res.reply, ui: res.ui }]);
        }
      } catch {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: "Sorry, something went wrong. Please try again." },
        ]);
      }
      setLoading(false);
    },
    [sessionId, loading, promptSignup]
  );

  const startSymptomTriage = useCallback(async () => {
    if (!sessionId || loading) return;
    setIntakeStarted(true);
    setLoading(true);
    try {
      const res = await api<{
        reply: string;
        emergency: boolean;
        ui?: ChatUiPayload | null;
        requires_signup?: boolean;
        signup_reason?: string;
      }>("/api/v1/guest/chat/messages", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, message: START_SYMPTOM_TRIAGE }),
      });
      if (res.requires_signup) {
        setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
        promptSignup(res.signup_reason);
      } else {
        setMessages((m) => [...m, { role: "assistant", content: res.reply, ui: res.ui }]);
      }
    } catch {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: "Sorry, something went wrong. Please try again." },
      ]);
    }
    setLoading(false);
  }, [sessionId, loading, promptSignup]);

  const onPick = (message: string) => {
    if (message === "Yes" || /book|appointment|doctor/i.test(message)) {
      promptSignup("booking");
      return;
    }
    setIntakeStarted(true);
    void sendText(message);
  };

  const handleQuickAction = (action: (typeof QUICK_ACTIONS)[number]) => {
    if (action.signup) {
      promptSignup(action.signup);
      return;
    }
    if (action.triage) {
      void startSymptomTriage();
    }
  };

  const lastAssistantIdx = messages.reduce(
    (last, msg, idx) => (msg.role === "assistant" ? idx : last),
    -1
  );

  const hasUserMessages = messages.some((m) => m.role === "user");
  const showWelcome = !hasUserMessages && !initError && !intakeStarted;

  return (
    <>
      <div className="aura-chat-widget">
        <button
          type="button"
          className="aura-chat-fab"
          onClick={() => onOpenChange(!open)}
          aria-label={open ? "Close consultation" : "Open AI consultation"}
        >
          <span className="material-symbols-outlined">smart_toy</span>
        </button>

        <div className={`aura-chat-window${open ? " aura-chat-window--open" : ""}`}>
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
                  <div className={`aura-chat-bubble${isUser ? " aura-chat-bubble--user" : " aura-chat-bubble--ai"}`}>
                    {isUser ? (
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
            <div className="aura-chat-input-wrap">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    const t = input.trim();
                    setInput("");
                    void sendText(t);
                  }
                }}
                placeholder="Type your health concern..."
                disabled={loading || !sessionId}
              />
              <button
                type="button"
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
              <button type="button" onClick={() => promptSignup()}>Verify email</button>
              {" · "}
              <Link to="/login">Sign in</Link>
            </p>
          </footer>
        </div>
      </div>

      <GuestSignupModal
        open={signupOpen}
        sessionId={sessionId}
        reason={signupReason}
        onClose={() => setSignupOpen(false)}
      />
    </>
  );
}
