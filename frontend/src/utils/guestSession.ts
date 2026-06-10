const GUEST_KEY = "guest_session_id";

export function getGuestSessionId(): string | null {
  return localStorage.getItem(GUEST_KEY);
}

export function setGuestSessionId(id: string) {
  localStorage.setItem(GUEST_KEY, id);
}

export async function ensureGuestSession(): Promise<string> {
  const existing = getGuestSessionId();
  if (existing) return existing;

  const { api } = await import("../api/client");
  const res = await api<{ session_id: string }>("/api/v1/guest/session", { method: "POST" });
  setGuestSessionId(res.session_id);
  return res.session_id;
}

export async function resetGuestSession(): Promise<string> {
  localStorage.removeItem(GUEST_KEY);
  return ensureGuestSession();
}
