export const WAV_OUTPUT_SAMPLE_RATE = 16_000;
export const WAV_CAPTURE_FLUSH_MS = 120;

export function resampleLinear(
  input: Float32Array,
  inputRate: number,
  outputRate: number,
): Float32Array {
  if (inputRate === outputRate || input.length === 0) {
    return input;
  }
  const outputLength = Math.max(1, Math.round((input.length * outputRate) / inputRate));
  const output = new Float32Array(outputLength);
  const ratio = inputRate / outputRate;
  for (let i = 0; i < outputLength; i += 1) {
    const srcIndex = i * ratio;
    const idx = Math.floor(srcIndex);
    const frac = srcIndex - idx;
    const a = input[idx] ?? 0;
    const b = input[Math.min(idx + 1, input.length - 1)] ?? a;
    output[i] = a + (b - a) * frac;
  }
  return output;
}

export function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const bitsPerSample = 16;
  const blockAlign = bitsPerSample / 8;
  const dataSize = samples.length * blockAlign;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeString = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i += 1) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  };

  writeString(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  writeString(36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i += 1) {
    const clamped = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, Math.round(clamped * 0x7fff), true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

export function mergePcmChunks(chunks: Float32Array[]): Float32Array {
  const total = chunks.reduce((sum, chunk) => sum + chunk.length, 0);
  const merged = new Float32Array(total);
  let writeOffset = 0;
  for (const chunk of chunks) {
    merged.set(chunk, writeOffset);
    writeOffset += chunk.length;
  }
  return merged;
}

export type StreamWavCapture = {
  blob: Blob;
  peak: number;
  samples: number;
  sampleRate: number;
  captureSampleRate: number;
};

export type StreamSizedWavCaptureHandle = {
  cancel: () => void;
};

function slicePcmForWavChunk(
  pcm: Float32Array,
  captureRate: number,
  targetOutputSamples: number,
): { nativeChunk: Float32Array; remainder: Float32Array } | null {
  if (pcm.length === 0) return null;

  let lo = 1;
  let hi = pcm.length;
  let best = pcm.length + 1;
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2);
    const len = resampleLinear(pcm.subarray(0, mid), captureRate, WAV_OUTPUT_SAMPLE_RATE).length;
    if (len >= targetOutputSamples) {
      best = mid;
      hi = mid - 1;
    } else {
      lo = mid + 1;
    }
  }
  if (best > pcm.length) return null;

  return {
    nativeChunk: pcm.subarray(0, best),
    remainder: pcm.subarray(best),
  };
}

/**
 * Continuously record a MediaStream; emit 16 kHz mono WAV chunks when each reaches targetWavBytes.
 * Does not stop stream tracks on cleanup — safe for LiveKit tracks.
 */
export function startStreamSizedWavCapture(
  stream: MediaStream,
  targetWavBytes: number,
  shouldAbort: () => boolean,
  onChunk: (capture: StreamWavCapture) => void,
): StreamSizedWavCaptureHandle {
  let cancelled = false;
  let ctx: AudioContext | null = null;
  let processor: ScriptProcessorNode | null = null;
  let source: MediaStreamAudioSourceNode | null = null;
  let pcmBuffer: Float32Array[] = [];
  let bufferedSamples = 0;
  let captureSampleRate = WAV_OUTPUT_SAMPLE_RATE;
  const targetOutputSamples = Math.max(1, Math.floor((Math.max(46, targetWavBytes) - 44) / 2));

  const cleanup = () => {
    processor!.onaudioprocess = null;
    try {
      processor?.disconnect();
    } catch {
      // ignore
    }
    try {
      source?.disconnect();
    } catch {
      // ignore
    }
    void ctx?.close();
    pcmBuffer = [];
    bufferedSamples = 0;
  };

  const tryFlush = () => {
    if (bufferedSamples === 0) return;
    const merged = mergePcmChunks(pcmBuffer);
    const sliced = slicePcmForWavChunk(merged, captureSampleRate, targetOutputSamples);
    if (!sliced) return;

    pcmBuffer = sliced.remainder.length > 0 ? [sliced.remainder] : [];
    bufferedSamples = sliced.remainder.length;

    let resampled = resampleLinear(
      sliced.nativeChunk,
      captureSampleRate,
      WAV_OUTPUT_SAMPLE_RATE,
    );
    if (resampled.length > targetOutputSamples) {
      resampled = resampled.subarray(0, targetOutputSamples);
    }

    let peak = 0;
    for (let i = 0; i < resampled.length; i += 1) {
      peak = Math.max(peak, Math.abs(resampled[i]));
    }

    onChunk({
      blob: encodeWav(resampled, WAV_OUTPUT_SAMPLE_RATE),
      peak: Number(peak.toFixed(4)),
      samples: resampled.length,
      sampleRate: WAV_OUTPUT_SAMPLE_RATE,
      captureSampleRate,
    });
  };

  void (async () => {
    try {
      ctx = new AudioContext();
      await ctx.resume();
      captureSampleRate = ctx.sampleRate;
      source = ctx.createMediaStreamSource(stream);
      processor = ctx.createScriptProcessor(4096, 1, 1);
      const silent = ctx.createGain();
      silent.gain.value = 0;

      processor.onaudioprocess = (event) => {
        if (cancelled || shouldAbort()) return;
        const channel = event.inputBuffer.getChannelData(0);
        pcmBuffer.push(new Float32Array(channel));
        bufferedSamples += channel.length;
        tryFlush();
      };

      source.connect(processor);
      processor.connect(silent);
      silent.connect(ctx.destination);
    } catch {
      cleanup();
    }
  })();

  return {
    cancel: () => {
      cancelled = true;
      cleanup();
    },
  };
}

/**
 * Record a MediaStream as 16 kHz mono WAV (resampled from the browser's native rate).
 * Does not stop stream tracks on cleanup — safe for LiveKit tracks.
 */
export function captureStreamWav(
  stream: MediaStream,
  durationMs: number,
  shouldAbort?: () => boolean,
): Promise<StreamWavCapture | null> {
  return new Promise((resolve, reject) => {
    void (async () => {
      let ctx: AudioContext | null = null;
      let processor: ScriptProcessorNode | null = null;
      let source: MediaStreamAudioSourceNode | null = null;
      let recordTimer: number | null = null;
      let flushTimer: number | null = null;

      const aborted = () => shouldAbort?.() ?? false;

      const cleanup = () => {
        if (recordTimer) clearTimeout(recordTimer);
        if (flushTimer) clearTimeout(flushTimer);
        processor!.onaudioprocess = null;
        try {
          processor?.disconnect();
        } catch {
          // ignore
        }
        try {
          source?.disconnect();
        } catch {
          // ignore
        }
        void ctx?.close();
      };

      try {
        ctx = new AudioContext();
        await ctx.resume();

        const captureSampleRate = ctx.sampleRate;
        source = ctx.createMediaStreamSource(stream);
        processor = ctx.createScriptProcessor(4096, 1, 1);
        const silent = ctx.createGain();
        silent.gain.value = 0;

        const pcmChunks: Float32Array[] = [];

        processor.onaudioprocess = (event) => {
          if (aborted()) return;
          const channel = event.inputBuffer.getChannelData(0);
          pcmChunks.push(new Float32Array(channel));
        };

        source.connect(processor);
        processor.connect(silent);
        silent.connect(ctx.destination);

        recordTimer = window.setTimeout(() => {
          flushTimer = window.setTimeout(() => {
            cleanup();
            if (aborted()) {
              resolve(null);
              return;
            }

            const captured = mergePcmChunks(pcmChunks);
            const resampled = resampleLinear(
              captured,
              captureSampleRate,
              WAV_OUTPUT_SAMPLE_RATE,
            );

            let peak = 0;
            for (let i = 0; i < resampled.length; i += 1) {
              peak = Math.max(peak, Math.abs(resampled[i]));
            }

            resolve({
              blob: encodeWav(resampled, WAV_OUTPUT_SAMPLE_RATE),
              peak: Number(peak.toFixed(4)),
              samples: resampled.length,
              sampleRate: WAV_OUTPUT_SAMPLE_RATE,
              captureSampleRate,
            });
          }, WAV_CAPTURE_FLUSH_MS);
        }, durationMs);
      } catch (err) {
        cleanup();
        reject(err);
      }
    })();
  });
}
