import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, setTokens } from "../api/client";
import EmailExistsNotice from "./EmailExistsNotice";
import { isEmailAlreadyExistsError, normalizeEmail } from "../utils/authErrors";

interface Props {
  open: boolean;
  sessionId: string | null;
  reason?: string;
  onClose: () => void;
}

export default function GuestSignupModal({ open, sessionId, reason, onClose }: Props) {
  const nav = useNavigate();
  const [step, setStep] = useState<"email" | "otp">("email");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [devOtp, setDevOtp] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [emailExists, setEmailExists] = useState(false);

  if (!open) return null;

  const sendOtp = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setEmailExists(false);
    setLoading(true);
    try {
      const normalizedEmail = normalizeEmail(email);
      const res = await api<{ message: string; dev_otp?: string }>("/api/v1/guest/auth/send-otp", {
        method: "POST",
        body: JSON.stringify({ email: normalizedEmail, name, session_id: sessionId }),
      });
      setEmail(normalizedEmail);
      if (res.dev_otp) setDevOtp(res.dev_otp);
      setStep("otp");
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : "Could not send code";
      if (isEmailAlreadyExistsError(errMsg)) {
        setEmailExists(true);
        setError("");
      } else {
        setEmailExists(false);
        setError(errMsg);
      }
    }
    setLoading(false);
  };

  const verifyOtp = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api<{
        access_token: string;
        refresh_token: string;
        user: { name: string; role: string };
        conversation_id?: string | null;
        resume_prompt?: string | null;
        pending_auth_action?: string | null;
      }>("/api/v1/guest/auth/verify-otp", {
        method: "POST",
        body: JSON.stringify({
          email,
          otp,
          name,
          session_id: sessionId,
        }),
      });
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
      onClose();
      nav("/chat", {
        replace: true,
        state: res.conversation_id
          ? {
              conversationId: res.conversation_id,
              fromGuestBooking: true,
            }
          : undefined,
      });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : "Verification failed";
      if (isEmailAlreadyExistsError(errMsg)) {
        setEmailExists(true);
        setStep("email");
        setError("");
      } else {
        setEmailExists(false);
        setError(errMsg);
      }
    }
    setLoading(false);
  };

  return (
    <div className="guest-modal-backdrop" role="dialog" aria-modal="true">
      <div className="guest-modal">
        <button type="button" className="guest-modal-close" onClick={onClose} aria-label="Close">
          <span className="material-symbols-outlined">close</span>
        </button>
        <h3>Create your free account</h3>
        <p className="guest-modal-sub">
          {reason === "booking"
            ? "Verify your email to book appointments and save your consultation."
            : "Verify your email to unlock booking, lab uploads, and your health dashboard."}
        </p>

        {step === "email" ? (
          <form onSubmit={(e) => void sendOtp(e)}>
            <label>
              Full name
              <input value={name} onChange={(e) => setName(e.target.value)} required minLength={2} />
            </label>
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setEmailExists(false);
                }}
                required
              />
            </label>
            {emailExists && (
              <EmailExistsNotice
                onSignIn={() => {
                  onClose();
                  nav("/login", { state: { view: "login", email: normalizeEmail(email) } });
                }}
                onForgotPassword={() => {
                  onClose();
                  nav("/login", { state: { view: "forgot", email: normalizeEmail(email) } });
                }}
              />
            )}
            {error && <p className="guest-modal-error">{error}</p>}
            <button type="submit" className="guest-modal-primary" disabled={loading}>
              {loading ? "Sending..." : "Send verification code"}
            </button>
          </form>
        ) : (
          <form onSubmit={(e) => void verifyOtp(e)}>
            <p className="guest-modal-hint">We sent a 6-digit code to <strong>{email}</strong></p>
            {devOtp && (
              <p className="guest-modal-dev">Dev code: <strong>{devOtp}</strong></p>
            )}
            <label>
              Verification code
              <input
                value={otp}
                onChange={(e) => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                required
                minLength={6}
                maxLength={6}
                inputMode="numeric"
                autoComplete="one-time-code"
              />
            </label>
            {error && <p className="guest-modal-error">{error}</p>}
            <button type="submit" className="guest-modal-primary" disabled={loading || otp.length < 6}>
              {loading ? "Verifying..." : "Verify & continue"}
            </button>
            <button type="button" className="guest-modal-link" onClick={() => setStep("email")}>
              Use a different email
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
