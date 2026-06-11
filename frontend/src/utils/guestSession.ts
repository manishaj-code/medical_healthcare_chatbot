const GUEST_KEY = "guest_session_id";
const SESSION_TIMEOUT_MS = 12_000;

function parsePersistFlag(raw: string | undefined, defaultValue = true): boolean {
  if (raw === undefined || raw === "") return defaultValue;
  return !["false", "0", "no", "off"].includes(raw.trim().toLowerCase());
}

/**
 * When true (default): guest session id is stored in localStorage and survives page refresh.
 * When false: each landing-page load starts a fresh MediAI guest session (dev/testing).
 * Set GUEST_SESSION_PERSIST in root .env (passed as VITE_GUEST_SESSION_PERSIST to the web container).
 */
export function isGuestSessionPersistEnabled(): boolean {
  return parsePersistFlag(import.meta.env.VITE_GUEST_SESSION_PERSIST as string | undefined, false);
}

export function getGuestSessionId(): string | null {
  if (!isGuestSessionPersistEnabled()) return null;
  return localStorage.getItem(GUEST_KEY);
}

export function setGuestSessionId(id: string) {
  if (!isGuestSessionPersistEnabled()) return;
  localStorage.setItem(GUEST_KEY, id);
}

function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error(message)), ms);
    promise
      .then((value) => {
        window.clearTimeout(timer);
        resolve(value);
      })
      .catch((err) => {
        window.clearTimeout(timer);
        reject(err);
      });
  });
}

async function createGuestSession(): Promise<string> {
  const { api } = await import("../api/client");
  const res = await withTimeout(
    api<{ session_id: string }>("/api/v1/guest/session", { method: "POST" }),
    SESSION_TIMEOUT_MS,
    "Could not reach the server. Is the API running?",
  );
  if (!res?.session_id) {
    throw new Error("Guest session response was invalid.");
  }
  setGuestSessionId(res.session_id);
  return res.session_id;
}

/** Return a live guest session id — re-create if Redis expired or Docker restarted. */
export async function ensureGuestSession(): Promise<string> {
  if (!isGuestSessionPersistEnabled()) {
    localStorage.removeItem(GUEST_KEY);
    return createGuestSession();
  }

  const { api } = await import("../api/client");
  const existing = getGuestSessionId();
  if (existing) {
    try {
      await withTimeout(
        api(`/api/v1/guest/chat/history?session_id=${encodeURIComponent(existing)}`),
        SESSION_TIMEOUT_MS,
        "Could not reach the server. Is the API running?",
      );
      return existing;
    } catch {
      localStorage.removeItem(GUEST_KEY);
    }
  }
  return createGuestSession();
}

export async function resetGuestSession(): Promise<string> {
  localStorage.removeItem(GUEST_KEY);
  return createGuestSession();
}
