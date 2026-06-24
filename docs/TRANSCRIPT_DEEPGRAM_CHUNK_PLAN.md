# Plan: `TRANSCRIPT_STT_PROVIDER=deepgram` (chunk mode)

Server-side Deepgram prerecorded transcription via LiveKit audio capture and REST chunk upload.

**Constraint:** With `deepgram` (not `deepgram_live`), use **~4–6 second** chunks per speaker — not 250ms. Deepgram `/v1/listen` works best on short utterances in the 3–10s range.

---

## Target flow

```text
LiveKit call (doctor + patient mics)
        ↓
Extract MediaStreamTrack per participant (local + remote)
        ↓
MediaRecorder cycles (~6s per speaker, parallel)
        ↓
POST /transcript/chunk  (multipart: audio + speaker_role + speaker_label)
        ↓
FastAPI → transcribe_audio_chunk() → Deepgram prerecorded (nova-3-medical)
        ↓
Save ConsultationTranscriptSegment + rebuild full_transcript_text
        ↓
POST /consultation/ai-from-transcript → analysis UI
```

**Do not use** browser-side Deepgram SDK in this mode — only `useTranscriptCapture` + `chunkRecorder.ts`.

---

## Current gaps

| Issue | Where | Fix |
|--------|--------|-----|
| Chunk interval mismatch | Frontend default 5s vs backend 6s | Use `sttConfig.chunk_interval_ms` from `transcript/start` |
| Min size mismatch | Frontend 1200 vs backend 1500 | Align to ~1400 bytes |
| Weak track access | Raw `mediaStreamTrack` | Use `publicationAudioTrack()` helper |
| No remote audio | Patient not joined / muted | Status UI + audio unlock |
| Consultation not started | `transcript/start` → 400 | Start consultation before transcript |
| Analysis with no text | Empty `full_transcript_text` | Gate Analyze on segments |

---

## Phase 0 — Configuration

```env
TRANSCRIPT_ENABLED=true
TRANSCRIPT_STT_PROVIDER=deepgram
TRANSCRIPT_CHUNK_MS=6000
DEEPGRAM_API_KEY=<key>
DEEPGRAM_MODEL=nova-3-medical
DEEPGRAM_LANGUAGE=en
DEEPGRAM_SMART_FORMAT=true
DEEPGRAM_LOG_REQUESTS=true   # while debugging
```

Validate `POST .../transcript/start` returns `provider: deepgram`, `available: true`, `chunk_interval_ms: 6000`.

---

## Phase 1 — LiveKit audio extraction

- Shared `listRoomAudioSources()` in `frontend/src/modules/video/utils/audioTracks.ts`
- Role from `identity` (`doctor:` / `patient:`) + metadata
- Re-bind capture on `onRoomChange`, participant join, mic toggle
- Preconditions: consultation started, room connected, transcript session active

---

## Phase 2 — Chunk capture hardening

- Chunk timing from `sttConfig.chunk_interval_ms` only
- Align `MIN_CHUNK_BYTES` frontend/backend (~1400)
- Keep AudioContext → MediaRecorder per track
- Upload queue with retry in `uploadChunk`
- Clear status messages in `TranscriptPanel`

---

## Phase 3 — Backend pipeline

- Shared `MIN_AUDIO_BYTES` in `stt_service.py`
- Structured skip reasons: `too_small`, `no_speech`, `duplicate`, `stt_error`
- Optional: no Groq fallback when `provider=deepgram`
- Stop/finalize session on modal close and consultation complete

---

## Phase 4 — Display & polling

- Poll `GET .../transcript` every 2.5s
- Empty state: speak ~6s with mic on

---

## Phase 5 — Analysis

- Enable Analyze when `segments.length >= 1`
- Auto-analyze: `MIN_SEGMENTS=1`, debounce ~12s for chunk mode
- Surface API errors clearly

---

## Task backlog

| ID | Task | Status |
|----|------|--------|
| D0.1 | Lock env: `deepgram` + `TRANSCRIPT_CHUNK_MS=6000` | done (.env.example) |
| D1.1 | Shared `listRoomAudioSources()` | done |
| D1.2 | Re-bind capture on join + mic toggle | done (onRoomChange + audioStatus deps) |
| D2.1 | Chunk interval from `sttConfig` only | done |
| D2.2 | Align min bytes frontend/backend | done (1400) |
| D2.3 | Upload queue + retry | done |
| D2.4 | TranscriptPanel status messages | done |
| D3.1 | Structured skip reasons | done |
| D3.2 | Disable Groq fallback for deepgram | done |
| D5.1 | Analyze gating + auto-analyze tuning | done |

---

## Testing checklist

1. `TRANSCRIPT_STT_PROVIDER=deepgram`, API restarted
2. Start consultation → video → both mics on → audio unlock
3. Panel shows “Listening to 2 audio sources”
4. Speak 8–10s → segment within ~6–12s
5. `POST /transcript/chunk` returns `segment`
6. Analyze works after segments exist

---

## Key files

| Area | Path |
|------|------|
| Capture | `frontend/src/modules/video/utils/chunkRecorder.ts` |
| Hook | `frontend/src/hooks/useTranscriptCapture.ts` |
| Audio utils | `frontend/src/modules/video/utils/audioTracks.ts` |
| UI | `frontend/src/components/doctor/TranscriptPanel.tsx` |
| STT | `backend/app/services/stt_service.py` |
| Ingest | `backend/app/services/consultation_transcript_service.py` |
