const API = import.meta.env.VITE_API_URL || "";

const AUTH_PATHS = [
  "/auth/login",
  "/auth/register",
  "/auth/refresh",
  "/auth/forgot-password",
  "/auth/reset-password",
];

function isAuthPath(path: string): boolean {
  return AUTH_PATHS.some((p) => path.includes(p));
}

function isGuestPath(path: string): boolean {
  return path.includes("/guest/");
}

export function getToken(): string | null {
  return localStorage.getItem("access_token");
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
}

export function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("user_role");
  localStorage.removeItem("user_name");
  localStorage.removeItem("mediai_history_recommendation");
}

async function refreshAccessToken(): Promise<string | null> {
  const refresh = localStorage.getItem("refresh_token");
  if (!refresh) return null;

  const res = await fetch(`${API}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });
  if (!res.ok) return null;

  const json = await res.json();
  const access = json.data?.access_token as string | undefined;
  if (!access) return null;

  localStorage.setItem("access_token", access);
  return access;
}

function parseError(res: Response, body: Record<string, unknown>): string {
  const detail = body.detail;
  if (typeof detail === "string") return detail;
  const err = body.error as { message?: string } | undefined;
  return err?.message || res.statusText || "Request failed";
}

export async function apiUpload<T>(path: string, formData: FormData, retry = true): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token && !isAuthPath(path) && !isGuestPath(path)) {
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${API}${path}`, { method: "POST", headers, body: formData });

  if (res.status === 401 && retry && !isAuthPath(path)) {
    const newToken = await refreshAccessToken();
    if (newToken) return apiUpload<T>(path, formData, false);
    clearTokens();
    if (!window.location.pathname.includes("/login")) {
      window.location.href = "/login";
    }
    throw new Error("Session expired. Please log in again.");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(parseError(res, body as Record<string, unknown>));
  }

  const json = await res.json();
  return json.data ?? json;
}

export async function api<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  // Do not send stale token on login/register — it causes 401 Invalid token
  if (token && !isAuthPath(path) && !isGuestPath(path)) {
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${API}${path}`, { ...options, headers });

  if (res.status === 401 && retry && !isAuthPath(path)) {
    const newToken = await refreshAccessToken();
    if (newToken) return api<T>(path, options, false);
    clearTokens();
    if (!window.location.pathname.includes("/login")) {
      window.location.href = "/login";
    }
    throw new Error("Session expired. Please log in again.");
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(parseError(res, body as Record<string, unknown>));
  }

  const json = await res.json();
  return json.data ?? json;
}
