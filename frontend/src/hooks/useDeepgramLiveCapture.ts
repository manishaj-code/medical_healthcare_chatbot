import { useEffect, useRef } from "react";
import { createClient, LiveTranscriptionEvents } from "@deepgram/sdk";
import type { ListenLiveClient } from "@deepgram/sdk";
import { useVideoRoom } from "../modules/video/hooks/useVideoRoom";
import { LiveKitService } from "../modules/video/services/livekitService";
import type { TranscriptSttConfig } from "../types/consultationTranscript";
import { deepgramLoggingEnabled, logDeepgramRequest, logDeepgramResponse } from "../utils/deepgramLog";

/** @deepgram/sdk references Node's `process` — shim for browser/Vite. */
function ensureBrowserProcessShim(): void {
  const g = globalThis as typeof globalThis & { process?: { env?: Record<string, string> } };
  if (typeof g.process === "undefined") {
    g.process = { env: {} };
  } else if (!g.process.env) {
    g.process.env = {};
  }
}

function createDeepgramClient(token: string) {
  ensureBrowserProcessShim();
  return createClient({ key: token });
}

type SpeakerSource = {
  key: string;
  role: "doctor" | "patient";
  label: string;
  track: MediaStreamTrack;
};

function parseParticipantRole(metadata: string | undefined): "doctor" | "patient" {
  if (!metadata) return "patient";
  try {
    const meta = JSON.parse(metadata) as { role?: string };
    return meta.role === "doctor" ? "doctor" : "patient";
  } catch {
    return "patient";
  }
}

function collectSpeakerSources(service: LiveKitService): SpeakerSource[] {
  const room = service.getRoom();
  if (!room) return [];

  const sources: SpeakerSource[] = [];
  const seen = new Set<string>();

  const local = room.localParticipant;
  if (local) {
    for (const publication of local.audioTrackPublications.values()) {
      const track = publication.track?.mediaStreamTrack;
      if (!track || track.readyState !== "live" || seen.has(track.id)) continue;
      seen.add(track.id);
      sources.push({
        key: `local-${track.id}`,
        role: "doctor",
        label: local.name || "You",
        track,
      });
    }
  }

  for (const [, participant] of room.remoteParticipants) {
    const role = parseParticipantRole(
      typeof participant.metadata === "string" ? participant.metadata : undefined,
    );
    const label = participant.name || (role === "doctor" ? "Doctor" : "Patient");

    for (const publication of participant.audioTrackPublications.values()) {
      const track = publication.track?.mediaStreamTrack;
      if (!track || track.readyState !== "live" || seen.has(track.id)) continue;
      seen.add(track.id);
      sources.push({
        key: `${participant.identity}-${track.id}`,
        role,
        label,
        track,
      });
    }
  }

  return sources;
}

type LiveConnection = {
  connection: ListenLiveClient;
  recorder: MediaRecorder;
};

const LIVE_SEND_MS = 250;

export function useDeepgramLiveCapture(
  enabled: boolean,
  stt: TranscriptSttConfig | null,
  onFinal: (text: string, speakerRole: string, speakerLabel: string, confidence?: number) => Promise<void>,
  onInterim?: (text: string, speakerRole: string, speakerLabel: string) => void,
) {
  const { service, connectionState, remoteParticipants, audioStatus } = useVideoRoom();
  const onFinalRef = useRef(onFinal);
  const onInterimRef = useRef(onInterim);
  onFinalRef.current = onFinal;
  onInterimRef.current = onInterim;

  useEffect(() => {
    const token = stt?.deepgram?.token;
    if (
      !enabled ||
      stt?.provider !== "deepgram_live" ||
      stt?.deepgram?.token_type !== "api_key" ||
      !token?.trim() ||
      connectionState !== "connected" ||
      !(service instanceof LiveKitService)
    ) {
      return undefined;
    }

    let destroyed = false;
    const liveConnections: LiveConnection[] = [];

    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/webm")
        ? "audio/webm"
        : "";

    const stopAll = () => {
      for (const item of liveConnections) {
        try {
          if (item.recorder.state !== "inactive") item.recorder.stop();
        } catch {
          // ignore
        }
        try {
          item.connection.requestClose();
        } catch {
          // ignore
        }
      }
      liveConnections.length = 0;
    };

    const startStreams = async () => {
      stopAll();
      if (destroyed || !mimeType) return;

      const room = service.getRoom();
      if (room && room.state === "connected") {
        try {
          await room.startAudio();
        } catch {
          // browser may require gesture
        }
      }

      const deepgram = createDeepgramClient(token);
      const sources = collectSpeakerSources(service);
      const dgLog = deepgramLoggingEnabled(stt);

      for (const source of sources) {
        try {
          const liveOptions = {
            model: stt.deepgram?.model || "nova-3-medical",
            language: stt.deepgram?.language || "en",
            smart_format: stt.deepgram?.smart_format ?? true,
            interim_results: stt.deepgram?.interim_results ?? true,
            punctuate: true,
          };

          if (dgLog) {
            logDeepgramRequest("listen_live_connect", {
              speaker: source.key,
              role: source.role,
              label: source.label,
              options: liveOptions,
            });
          }

          const connection = deepgram.listen.live(liveOptions);

          connection.on(LiveTranscriptionEvents.Transcript, (data) => {
            const alt = data.channel?.alternatives?.[0];
            const transcript = alt?.transcript?.trim();
            if (!transcript) return;

            if (dgLog) {
              logDeepgramResponse("listen_live_transcript", {
                speaker: source.key,
                role: source.role,
                label: source.label,
                is_final: data.is_final,
                transcript,
                confidence: alt?.confidence,
                raw: data,
              });
            }

            if (data.is_final) {
              void onFinalRef.current(
                transcript,
                source.role,
                source.label,
                alt?.confidence,
              );
            } else {
              onInterimRef.current?.(transcript, source.role, source.label);
            }
          });

          connection.on(LiveTranscriptionEvents.Error, (err) => {
            if (dgLog) {
              logDeepgramResponse("listen_live_error", {
                speaker: source.key,
                role: source.role,
                label: source.label,
                error: err,
              });
            }
            console.warn("Deepgram live error", source.key, err);
          });

          const stream = new MediaStream([source.track]);
          const recorder = new MediaRecorder(stream, {
            mimeType,
            audioBitsPerSecond: 128_000,
          });

          recorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
              if (dgLog) {
                logDeepgramRequest("listen_live_audio_chunk", {
                  speaker: source.key,
                  role: source.role,
                  label: source.label,
                  bytes: event.data.size,
                  mime_type: event.data.type || mimeType,
                });
              }
              try {
                connection.send(event.data);
              } catch (sendErr) {
                if (dgLog) {
                  logDeepgramResponse("listen_live_send_error", {
                    speaker: source.key,
                    error: sendErr,
                  });
                }
              }
            }
          };

          connection.on(LiveTranscriptionEvents.Open, () => {
            if (dgLog) {
              logDeepgramResponse("listen_live_open", {
                speaker: source.key,
                role: source.role,
                label: source.label,
              });
            }
            if (destroyed) return;
            try {
              recorder.start(LIVE_SEND_MS);
            } catch {
              // ignore
            }
          });

          liveConnections.push({ connection, recorder });
        } catch (err) {
          console.warn("Could not start Deepgram stream for", source.key, err);
        }
      }
    };

    void startStreams();

    const unsubscribe =
      service instanceof LiveKitService
        ? service.onRoomChange(() => {
            void startStreams();
          })
        : () => undefined;

    return () => {
      destroyed = true;
      unsubscribe();
      stopAll();
    };
  }, [
    enabled,
    stt,
    connectionState,
    service,
    remoteParticipants.length,
    audioStatus.length,
  ]);
}
