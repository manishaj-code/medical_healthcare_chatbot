import { useEffect, useRef, useState } from "react";
import { useVideoRoom } from "../modules/video/hooks/useVideoRoom";
import { LiveKitService } from "../modules/video/services/livekitService";
import {
  listCaptureSources,
  startTranscriptCapture,
  TRANSCRIPT_CHUNK_MS,
} from "./transcriptAudioCapture";

export function useTranscriptCapture(
  enabled: boolean,
  onChunk: (blob: Blob, speakerRole: string, speakerLabel: string) => Promise<void>,
  chunkMs = TRANSCRIPT_CHUNK_MS,
) {
  const { service, connectionState, remoteParticipants, audioStatus } = useVideoRoom();
  const onChunkRef = useRef(onChunk);
  const [sourceCount, setSourceCount] = useState(0);
  onChunkRef.current = onChunk;

  useEffect(() => {
    if (
      !enabled ||
      connectionState !== "connected" ||
      !(service instanceof LiveKitService)
    ) {
      setSourceCount(0);
      return undefined;
    }

    let capture: Awaited<ReturnType<typeof startTranscriptCapture>> | null = null;
    let cancelled = false;

    void (async () => {
      capture = await startTranscriptCapture(
        service,
        (blob, role, label) => onChunkRef.current(blob, role, label),
        chunkMs,
      );
      if (cancelled) {
        capture?.stop();
        return;
      }
      setSourceCount(capture?.sourceCount ?? listCaptureSources(service).length);
    })();

    const poll = window.setInterval(() => {
      if (service instanceof LiveKitService) {
        setSourceCount(listCaptureSources(service).length);
      }
    }, 2_000);

    return () => {
      cancelled = true;
      window.clearInterval(poll);
      capture?.stop();
      setSourceCount(0);
    };
  }, [
    enabled,
    connectionState,
    service,
    remoteParticipants.length,
    audioStatus.length,
    chunkMs,
  ]);

  return { sourceCount };
}
