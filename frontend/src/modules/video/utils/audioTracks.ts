import type { LocalParticipant, RemoteParticipant, TrackPublication } from "livekit-client";
import { Room, Track } from "livekit-client";

export type RoomAudioSource = {
  key: string;
  role: "doctor" | "patient";
  label: string;
  track: MediaStreamTrack;
};

/** Must stay aligned with backend `MIN_AUDIO_BYTES` in stt_service.py */
export const MIN_TRANSCRIPT_CHUNK_BYTES = 1_400;

/** Default WAV chunk size: 16 kHz mono 16-bit ≈ 6s (44 + 96000×2 bytes). Align with backend `transcript_chunk_bytes`. */
export const TRANSCRIPT_CHUNK_BYTES_DEFAULT = 192_044;

export function formatTranscriptChunkBytes(bytes: number): string {
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`;
  return `${Math.round(bytes / 1024)} KB`;
}

export function parseParticipantRole(
  metadata: string | undefined,
  identity?: string,
): "doctor" | "patient" {
  if (identity?.startsWith("doctor:")) return "doctor";
  if (identity?.startsWith("patient:")) return "patient";
  if (!metadata) return "patient";
  try {
    const meta = JSON.parse(metadata) as { role?: string };
    return meta.role === "doctor" ? "doctor" : "patient";
  } catch {
    return "patient";
  }
}

/** Resolve a subscribed LiveKit audio publication to a browser MediaStreamTrack. */
export function getPublicationAudioTrack(publication: TrackPublication): MediaStreamTrack | null {
  const track = publication.track;
  if (!track) {
    return null;
  }
  if (track instanceof MediaStreamTrack) {
    return track.readyState === "ended" ? null : track;
  }
  const mediaTrack = track.mediaStreamTrack;
  if (!mediaTrack || mediaTrack.readyState === "ended") {
    return null;
  }
  return mediaTrack;
}

function participantLabel(
  participant: LocalParticipant | RemoteParticipant,
  role: "doctor" | "patient",
  isLocal: boolean,
): string {
  if (participant.name?.trim()) {
    return participant.name.trim();
  }
  if (isLocal) return "You";
  return role === "doctor" ? "Doctor" : "Patient";
}

function collectFromParticipant(
  participant: LocalParticipant | RemoteParticipant,
  isLocal: boolean,
  seen: Set<string>,
  sources: RoomAudioSource[],
): void {
  const metadata = typeof participant.metadata === "string" ? participant.metadata : undefined;
  const role = parseParticipantRole(metadata, participant.identity);
  const label = participantLabel(participant, role, isLocal);
  const prefix = isLocal ? "local" : participant.identity;

  for (const publication of participant.audioTrackPublications.values()) {
    if (publication.kind !== Track.Kind.Audio) continue;
    if (publication.isMuted) continue;
    const track = getPublicationAudioTrack(publication);
    if (!track || seen.has(track.id)) continue;
    seen.add(track.id);
    sources.push({
      key: `${prefix}-${track.id}`,
      role,
      label,
      track,
    });
  }
}

/** All live microphone tracks in the room (local + remote). */
export function listRoomAudioSources(room: Room | null | undefined): RoomAudioSource[] {
  if (!room) return [];

  const sources: RoomAudioSource[] = [];
  const seen = new Set<string>();

  if (room.localParticipant) {
    collectFromParticipant(room.localParticipant, true, seen, sources);
  }

  for (const [, participant] of room.remoteParticipants) {
    collectFromParticipant(participant, false, seen, sources);
  }

  return sources;
}

export function listRoomAudioSourceMeta(
  room: Room | null | undefined,
): Pick<RoomAudioSource, "key" | "role" | "label">[] {
  return listRoomAudioSources(room).map(({ key, role, label }) => ({ key, role, label }));
}
