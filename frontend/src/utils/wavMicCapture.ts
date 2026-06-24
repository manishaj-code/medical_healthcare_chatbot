import { captureStreamWav } from "./wavEncode";

export type MicWavCapture = {
  blob: Blob;
  peak: number;
  samples: number;
  sampleRate: number;
  captureSampleRate: number;
};

/** Record microphone as 16 kHz mono WAV (resampled from the browser's native rate). */
export function captureMicWav(durationMs: number): Promise<MicWavCapture> {
  return new Promise((resolve, reject) => {
    void (async () => {
      let stream: MediaStream | null = null;

      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: false,
            noiseSuppression: false,
            autoGainControl: true,
          },
        });

        const captured = await captureStreamWav(stream, durationMs);
        stream.getTracks().forEach((t) => t.stop());

        if (!captured) {
          reject(new Error("Microphone capture aborted"));
          return;
        }

        resolve(captured);
      } catch (err) {
        stream?.getTracks().forEach((t) => t.stop());
        reject(err);
      }
    })();
  });
}
