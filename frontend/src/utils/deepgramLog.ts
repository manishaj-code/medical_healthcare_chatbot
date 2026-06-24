/** Optional console logging for Deepgram (chunk mode uses server-side STT only). */

export function deepgramLoggingEnabled(): boolean {
  return import.meta.env.DEV;
}

export function logDeepgramRequest(
  operation: string,
  payload?: Record<string, unknown>,
): void {
  if (!deepgramLoggingEnabled()) return;
  console.info("[Deepgram request]", { operation, ...payload });
}

export function logDeepgramResponse(
  operation: string,
  payload?: Record<string, unknown>,
): void {
  if (!deepgramLoggingEnabled()) return;
  console.info("[Deepgram response]", { operation, ...payload });
}
