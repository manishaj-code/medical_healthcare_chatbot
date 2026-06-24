export function mapTranscriptAnalyzeError(message: string): string {
  const lower = message.toLowerCase();
  if (lower.includes("no transcript")) {
    return "No speech captured yet — wait for transcript lines after the next audio chunk.";
  }
  if (lower.includes("llm api") || lower.includes("groq_api") || lower.includes("gemini")) {
    return "AI analysis unavailable — check GROQ_API_KEY or GEMINI_API_KEY on the server.";
  }
  if (lower.includes("start consultation")) {
    return "Start the consultation before analyzing the transcript.";
  }
  return message;
}

export function mapTranscriptUploadError(message: string): string {
  const lower = message.toLowerCase();
  if (lower.includes("not started") || lower.includes("session not started")) {
    return "Transcript session is not active — reopen the video call.";
  }
  if (lower.includes("503") || lower.includes("disabled")) {
    return "Transcription is disabled on the server.";
  }
  if (lower.includes("missing_deepgram_key") || lower.includes("not configured")) {
    return "Deepgram is not configured on the server (DEEPGRAM_API_KEY).";
  }
  if (lower.includes("corrupt or unsupported")) {
    return "Audio chunk could not be decoded — keep speaking for the full chunk interval (~6s).";
  }
  if (lower.includes("deepgram http 401")) {
    return "Invalid Deepgram API key — update DEEPGRAM_API_KEY and restart the API.";
  }
  return message;
}
