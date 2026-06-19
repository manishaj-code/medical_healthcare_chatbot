import type { ParticipantInfo } from '../types';

/**
 * Abstract video service interface.
 * Implementations (e.g., LiveKitService, TwilioService) must provide these methods.
 * The interface is intentionally provider‑agnostic and does not know about
 * doctors, patients, appointments, or any other domain concepts.
 */
export abstract class VideoService {
  /** Initialize the service with a token and provider URL. */
  abstract initialize(token: string, url?: string, roomId?: string): Promise<void>;

  /** Join the room. Must be called after initialize. */
  abstract joinRoom(): Promise<void>;

  /** Leave the room and clean up resources. */
  abstract leaveRoom(): Promise<void>;

  /** Return the local audio and video tracks (if published). */
  abstract getLocalTracks(): Promise<MediaStreamTrack[]>;

  /** Publish a local track (audio/video) if not already published. */
  abstract publishTrack(track: MediaStreamTrack): Promise<void>;

  /** Unpublish a local track. */
  abstract unpublishTrack(track: MediaStreamTrack): Promise<void>;

  /** Set whether the local microphone is enabled. */
  abstract setAudioEnabled(enabled: boolean): Promise<void>;

  /** Set whether the local camera is enabled. */
  abstract setVideoEnabled(enabled: boolean): Promise<void>;

  /** Share the screen (or a specific window/application). */
  abstract shareScreen(): Promise<void>;

  /** Stop sharing the screen. */
  abstract stopShareScreen(): Promise<void>;

  /** Send arbitrary data to all participants (if provider supports data messages). */
  abstract sendData(data: Uint8Array | string): Promise<void>;

  /** Get list of remote participants currently in the room. */
  abstract getRemoteParticipants(): Promise<ParticipantInfo[]>;

  /**
   * Get tracks (audio/video) for a specific remote participant.
   * Returns an array of MediaStreamTrack (could be empty if no tracks yet).
   */
  abstract getParticipantTracks(participantId: string): Promise<MediaStreamTrack[]>;

  /** Remote audio tracks for a participant (used for playback). */
  abstract getParticipantAudioTracks(participantId: string): Promise<MediaStreamTrack[]>;

  /** Mic on/off status for UI indicators. */
  abstract getAudioStatus(): { participant_id: string; label: string; mic_active: boolean; is_local: boolean }[];

  /** Get the current connection state (e.g., connecting, connected, disconnected, failed). */
  abstract getConnectionState(): string;

  /** Get any connection error if state is failed. */
  abstract getError(): Error | null;

  /** Unlock browser audio playback (required after user gesture on some browsers). */
  abstract ensureAudioPlayback(): Promise<void>;

  /** Local mic/camera toggle state for control UI. */
  abstract getLocalMediaState(): { micEnabled: boolean; cameraEnabled: boolean };
}