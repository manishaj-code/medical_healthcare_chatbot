import type { LiveKitService } from "../modules/video/services/livekitService";

export const TRANSCRIPT_CHUNK_MS = 5_000;
export const MIN_CHUNK_BYTES = 1_200;

export type CaptureSource = {
  key: string;
  role: "doctor" | "patient";
  label: string;
};

export type ChunkHandler = (
  blob: Blob,
  role: "doctor" | "patient",
  label: string,
) => void | Promise<void>;

function parseRole(metadata: string | undefined, identity?: string): "doctor" | "patient" {
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

function pickMimeType(): string {
  if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) return "audio/webm;codecs=opus";
  if (MediaRecorder.isTypeSupported("audio/webm")) return "audio/webm";
  return "";
}

export function listCaptureSources(service: LiveKitService): CaptureSource[] {
  const room = service.getRoom();
  if (!room) return [];

  const sources: CaptureSource[] = [];
  const seen = new Set<string>();

  const local = room.localParticipant;
  if (local) {
    for (const publication of local.audioTrackPublications.values()) {
      const track = publication.track?.mediaStreamTrack;
      if (!track || track.readyState !== "live" || seen.has(track.id)) continue;
      if (publication.isMuted || track.muted) continue;
      seen.add(track.id);
      const role = parseRole(
        typeof local.metadata === "string" ? local.metadata : undefined,
        local.identity,
      );
      sources.push({ key: `local-${track.id}`, role, label: local.name || "You" });
    }
  }

  for (const [, participant] of room.remoteParticipants) {
    const role = parseRole(
      typeof participant.metadata === "string" ? participant.metadata : undefined,
      participant.identity,
    );
    const label = participant.name || (role === "doctor" ? "Doctor" : "Patient");

    for (const publication of participant.audioTrackPublications.values()) {
      const track = publication.track?.mediaStreamTrack;
      if (!track || track.readyState !== "live" || seen.has(track.id)) continue;
      if (publication.isMuted || track.muted) continue;
      seen.add(track.id);
      sources.push({ key: `${participant.identity}-${track.id}`, role, label });
    }
  }

  return sources;
}

type SourceRecorder = {
  key: string;
  role: "doctor" | "patient";
  label: string;
  track: MediaStreamTrack;
};

function listSourceRecorders(service: LiveKitService): SourceRecorder[] {
  const room = service.getRoom();
  if (!room) return [];

  const recorders: SourceRecorder[] = [];
  const seen = new Set<string>();

  const local = room.localParticipant;
  if (local) {
    for (const publication of local.audioTrackPublications.values()) {
      const track = publication.track?.mediaStreamTrack;
      if (!track || track.readyState !== "live" || seen.has(track.id)) continue;
      if (publication.isMuted || track.muted) continue;
      seen.add(track.id);
      recorders.push({
        key: `local-${track.id}`,
        role: parseRole(
          typeof local.metadata === "string" ? local.metadata : undefined,
          local.identity,
        ),
        label: local.name || "You",
        track,
      });
    }
  }

  for (const [, participant] of room.remoteParticipants) {
    const role = parseRole(
      typeof participant.metadata === "string" ? participant.metadata : undefined,
      participant.identity,
    );
    const label = participant.name || (role === "doctor" ? "Doctor" : "Patient");

    for (const publication of participant.audioTrackPublications.values()) {
      const track = publication.track?.mediaStreamTrack;
      if (!track || track.readyState !== "live" || seen.has(track.id)) continue;
      if (publication.isMuted || track.muted) continue;
      seen.add(track.id);
      recorders.push({
        key: `${participant.identity}-${track.id}`,
        role,
        label,
        track,
      });
    }
  }

  return recorders;
}

type RecorderCycle = { cancel: () => void };

function startRecorderCycle(
  audioContext: AudioContext,
  source: SourceRecorder,
  mimeType: string,
  chunkMs: number,
  isDestroyed: () => boolean,
  onChunk: ChunkHandler,
): RecorderCycle {
  let recorder: MediaRecorder | null = null;
  let recordTimer: ReturnType<typeof setTimeout> | null = null;
  let gapTimer: ReturnType<typeof setTimeout> | null = null;
  let cancelled = false;
  let sourceNode: MediaStreamAudioSourceNode | null = null;
  let destination: MediaStreamAudioDestinationNode | null = null;

  const clearTimers = () => {
    if (recordTimer) clearTimeout(recordTimer);
    if (gapTimer) clearTimeout(gapTimer);
    recordTimer = null;
    gapTimer = null;
  };

  const cleanupNodes = () => {
    try {
      sourceNode?.disconnect();
    } catch {
      // ignore
    }
    try {
      destination?.disconnect();
    } catch {
      // ignore
    }
    sourceNode = null;
    destination = null;
  };

  const scheduleNext = () => {
    if (cancelled || isDestroyed()) return;
    gapTimer = window.setTimeout(() => void runCycle(), 120);
  };

  const runCycle = async () => {
    if (cancelled || isDestroyed()) return;
    if (source.track.readyState !== "live" || source.track.muted) {
      scheduleNext();
      return;
    }

    try {
      if (audioContext.state === "suspended") {
        await audioContext.resume();
      }
    } catch {
      // ignore
    }

    const parts: BlobPart[] = [];
    cleanupNodes();

    try {
      destination = audioContext.createMediaStreamDestination();
      sourceNode = audioContext.createMediaStreamSource(new MediaStream([source.track]));
      sourceNode.connect(destination);
      recorder = new MediaRecorder(destination.stream, {
        mimeType,
        audioBitsPerSecond: 96_000,
      });
    } catch {
      scheduleNext();
      return;
    }

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) parts.push(event.data);
    };

    recorder.onstop = () => {
      cleanupNodes();
      const blob = new Blob(parts, { type: mimeType });
      if (blob.size >= MIN_CHUNK_BYTES) {
        void onChunk(blob, source.role, source.label);
      }
      scheduleNext();
    };

    recorder.onerror = () => {
      cleanupNodes();
      scheduleNext();
    };

    try {
      recorder.start();
      recordTimer = window.setTimeout(() => {
        if (recorder?.state === "recording") {
          try {
            recorder.requestData();
          } catch {
            // ignore
          }
          recorder.stop();
        }
      }, chunkMs);
    } catch {
      cleanupNodes();
      scheduleNext();
    }
  };

  void runCycle();

  return {
    cancel: () => {
      cancelled = true;
      clearTimers();
      if (recorder?.state === "recording") {
        try {
          recorder.stop();
        } catch {
          // ignore
        }
      }
      recorder = null;
      cleanupNodes();
    },
  };
}

export type TranscriptCaptureSession = {
  sourceCount: number;
  stop: () => void;
};

export async function startTranscriptCapture(
  service: LiveKitService,
  onChunk: ChunkHandler,
  chunkMs = TRANSCRIPT_CHUNK_MS,
): Promise<TranscriptCaptureSession | null> {
  const mimeType = pickMimeType();
  if (!mimeType) return null;

  const room = service.getRoom();
  if (room?.state === "connected") {
    try {
      await room.startAudio();
    } catch {
      // gesture may be required
    }
  }

  const audioContext = new AudioContext();
  try {
    await audioContext.resume();
  } catch {
    // ignore
  }

  let destroyed = false;
  const cycles: RecorderCycle[] = [];

  const bind = () => {
    for (const cycle of cycles) cycle.cancel();
    cycles.length = 0;

    if (destroyed) return;

    const sources = listSourceRecorders(service);
    for (const source of sources) {
      cycles.push(
        startRecorderCycle(
          audioContext,
          source,
          mimeType,
          chunkMs,
          () => destroyed,
          onChunk,
        ),
      );
    }
  };

  bind();
  const unsubscribe = service.onRoomChange(bind);

  return {
    sourceCount: listCaptureSources(service).length,
    stop: () => {
      destroyed = true;
      unsubscribe();
      for (const cycle of cycles) cycle.cancel();
      cycles.length = 0;
      void audioContext.close();
    },
  };
}
