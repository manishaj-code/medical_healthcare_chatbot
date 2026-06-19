import type { TranscriptSttConfig } from "../types/consultationTranscript";

export function deepgramLoggingEnabled(stt: TranscriptSttConfig | null | undefined): boolean {
  return Boolean(stt?.deepgram_log_requests);
}

export function logDeepgramRequest(
  operation: string,
  payload: Record<string, unknown>,
): void {
  console.info("[Deepgram request]", { operation, ...payload });
}

export function logDeepgramResponse(
  operation: string,
  payload: Record<string, unknown>,
): void {
  console.info("[Deepgram response]", { operation, ...payload });
}
