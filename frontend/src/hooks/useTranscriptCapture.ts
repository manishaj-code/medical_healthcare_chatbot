import { useEffect, useRef, useState } from "react";
import { useVideoRoom } from "../modules/video/hooks/useVideoRoom";
import { LiveKitService } from "../modules/video/services/livekitService";
import { listRoomAudioSources, MIN_TRANSCRIPT_CHUNK_BYTES, TRANSCRIPT_CHUNK_BYTES_DEFAULT } from "../modules/video/utils/audioTracks";
import {
  startChunkRecorder,
  type ChunkHandler,
} from "../modules/video/utils/chunkRecorder";

export function useTranscriptCapture(
  enabled: boolean,
  onChunk: ChunkHandler,
  chunkBytes: number,
) {
  const { service, connectionState, remoteParticipants, audioStatus } = useVideoRoom();
  const onChunkRef = useRef(onChunk);
  const [sourceCount, setSourceCount] = useState(0);
  onChunkRef.current = onChunk;

  const effectiveChunkBytes =
    chunkBytes >= MIN_TRANSCRIPT_CHUNK_BYTES ? chunkBytes : TRANSCRIPT_CHUNK_BYTES_DEFAULT;

  useEffect(() => {
    if (
      !enabled ||
      connectionState !== "connected" ||
      !(service instanceof LiveKitService) ||
      effectiveChunkBytes < MIN_TRANSCRIPT_CHUNK_BYTES
    ) {
      setSourceCount(0);
      return undefined;
    }

    let destroyed = false;
    const recorders: ReturnType<typeof startChunkRecorder>[] = [];

    const bind = async () => {
      for (const recorder of recorders) recorder.cancel();
      recorders.length = 0;
      if (destroyed) return;

      const room = service.getRoom();
      if (room?.state === "connected") {
        try {
          await room.startAudio();
        } catch {
          // browser may require user gesture
        }
      }

      const sources = listRoomAudioSources(service.getRoom());
      for (const source of sources) {
        recorders.push(
          startChunkRecorder(
            source,
            effectiveChunkBytes,
            () => destroyed,
            (blob, role, label) => onChunkRef.current(blob, role, label),
          ),
        );
      }
      setSourceCount(sources.length);
    };

    void bind();
    const unsubscribe = service.onRoomChange(() => void bind());
    const poll = window.setInterval(() => {
      setSourceCount(listRoomAudioSources(service.getRoom()).length);
    }, 2_000);

    return () => {
      destroyed = true;
      unsubscribe();
      window.clearInterval(poll);
      for (const recorder of recorders) recorder.cancel();
      recorders.length = 0;
      setSourceCount(0);
    };
  }, [
    enabled,
    connectionState,
    service,
    remoteParticipants.length,
    audioStatus.length,
    effectiveChunkBytes,
  ]);

  return { sourceCount };
}
