import { startStreamSizedWavCapture } from "../../../utils/wavEncode";
import {
  MIN_TRANSCRIPT_CHUNK_BYTES,
  type RoomAudioSource,
} from "./audioTracks";

export type ChunkHandler = (
  blob: Blob,
  role: "doctor" | "patient",
  label: string,
) => void;

export type ChunkRecorderHandle = {
  cancel: () => void;
};

/**
 * Record a LiveKit mic track as 16 kHz WAV chunks; emit each chunk when it reaches targetBytes.
 */
export function startChunkRecorder(
  source: RoomAudioSource,
  targetBytes: number,
  isDestroyed: () => boolean,
  onChunk: ChunkHandler,
): ChunkRecorderHandle {
  const track = source.track;

  if (track.readyState !== "live") {
    return { cancel: () => undefined };
  }

  const stream = new MediaStream([track]);

  return startStreamSizedWavCapture(
    stream,
    targetBytes,
    () => isDestroyed() || track.readyState !== "live",
    (captured) => {
      if (track.muted) return;
      if (captured.blob.size < MIN_TRANSCRIPT_CHUNK_BYTES) return;
      onChunk(captured.blob, source.role, source.label);
    },
  );
}
