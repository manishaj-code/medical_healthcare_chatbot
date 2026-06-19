export interface TokenResponse {
  /** Signed token granting access to the room for a participant. */
  token: string;
  /** Provider‑specific connection URL (e.g., LiveKit WS endpoint). */
  url?: string | null;
  /** Time‑to‑live for the token in seconds (if known). */
  ttl?: number | null;
}