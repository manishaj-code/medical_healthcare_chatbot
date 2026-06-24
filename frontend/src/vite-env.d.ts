/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_GUEST_SESSION_PERSIST?: string;
  readonly VITE_LIVEKIT_URL?: string;
  readonly VITE_DEEPGRAM_API_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
