import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import type { ToastItem } from "./ToastProvider";

const EXIT_MS = 320;

interface Props {
  toast: ToastItem;
  onDismiss: (id: string) => void;
}

const VARIANT_FALLBACK: Record<NonNullable<ToastItem["variant"]>, string> = {
  success: "Confirmed",
  error: "Alert",
  urgent: "Urgent",
  info: "Update",
};

export default function ToastCard({ toast, onDismiss }: Props) {
  const variant = toast.variant ?? "info";
  const duration = toast.durationMs ?? 7000;
  const [exiting, setExiting] = useState(false);
  const [paused, setPaused] = useState(false);
  const timerRef = useRef<number | null>(null);
  const remainingRef = useRef(duration);
  const startedAtRef = useRef(Date.now());

  const dismiss = useCallback(() => {
    if (exiting) return;
    setExiting(true);
    window.setTimeout(() => onDismiss(toast.id), EXIT_MS);
  }, [exiting, onDismiss, toast.id]);

  const clearTimer = () => {
    if (timerRef.current) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const startTimer = useCallback(
    (ms: number) => {
      clearTimer();
      startedAtRef.current = Date.now();
      remainingRef.current = ms;
      timerRef.current = window.setTimeout(() => dismiss(), ms);
    },
    [dismiss],
  );

  useEffect(() => {
    startTimer(duration);
    return clearTimer;
  }, [duration, startTimer]);

  const handleMouseEnter = () => {
    if (paused || exiting) return;
    setPaused(true);
    const elapsed = Date.now() - startedAtRef.current;
    remainingRef.current = Math.max(0, remainingRef.current - elapsed);
    clearTimer();
  };

  const handleMouseLeave = () => {
    if (!paused || exiting) return;
    setPaused(false);
    startTimer(remainingRef.current);
  };

  const showLiveDot = variant === "urgent";

  return (
    <article
      className={`toast toast--${variant}${exiting ? " toast--exit" : " toast--enter"}`}
      role="status"
      style={{ "--toast-duration": `${duration}ms` } as CSSProperties}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div className="toast-frame" aria-hidden />
      <div className="toast-shimmer" aria-hidden />

      <div className="toast-body">
        <div className="toast-icon-wrap" aria-hidden>
          <span className="toast-icon-ring" />
          <span className="toast-icon">
            <span className="material-symbols-outlined filled-icon">{toast.icon ?? "notifications"}</span>
          </span>
        </div>

        <div className="toast-content">
          <div className="toast-head">
            <div className="toast-head-main">
              <span className={`toast-chip toast-chip--${variant}`}>
                {toast.chipLabel ?? VARIANT_FALLBACK[variant]}
              </span>
              {showLiveDot && <span className="toast-live-dot" aria-hidden />}
              <span className="toast-time">Just now</span>
            </div>
            <button
              type="button"
              className="toast-close"
              onClick={dismiss}
              aria-label="Dismiss notification"
            >
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>
          <p className="toast-title">{toast.title}</p>
          <p className="toast-message">{toast.message}</p>
        </div>
      </div>

      <div className={`toast-progress${paused ? " toast-progress--paused" : ""}`} aria-hidden />
    </article>
  );
}
