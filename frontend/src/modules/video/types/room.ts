export interface RoomCreateRequest {
  /** Opaque identifier for the room chosen by the host application (e.g., appointment UUID). */
  room_id: string;
  /** Arbitrary data the host wishes to store with the room (if the provider supports it). */
  metadata?: Record<string, unknown> | null;
}

export interface RoomResponse {
  /** The same opaque identifier passed in the request. */
  room_id: string;
  /** Identifier used internally by the video provider (if different). */
  provider_room_id?: string | null;
  /** ISO‑8601 timestamp when the room was created (if known). */
  created_at?: string | null;
  /** Echo of the metadata supplied on creation (if the provider stores it). */
  metadata?: Record<string, unknown> | null;
}