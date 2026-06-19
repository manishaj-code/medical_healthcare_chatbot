export interface ParticipantInfo {
  /** Opaque identifier for the participant (user) chosen by the host application. */
  participant_id: string;
  /** Display name from the video provider token. */
  name?: string;
  /** Role string as understood by the video provider (e.g., host, guest, moderator). */
  role: string;
  /** Optional metadata that was embedded in the token by the provider. */
  metadata?: Record<string, unknown> | null;
}