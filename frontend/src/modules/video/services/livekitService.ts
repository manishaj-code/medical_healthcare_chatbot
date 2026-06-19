import { Room, LocalParticipant, RemoteParticipant, RemoteTrack, Track, TrackPublication, ConnectionState, DisconnectReason, RoomEvent } from 'livekit-client';
import type { ParticipantInfo } from '../types';
import { VideoService } from '../interfaces/videoService';

function publicationMediaTrack(publication: TrackPublication): MediaStreamTrack | null {
  const track = publication.track;
  if (!track || publication.isMuted) {
    return null;
  }
  if (track instanceof MediaStreamTrack) {
    return track;
  }
  const mediaTrack = (track as Track).mediaStreamTrack;
  return mediaTrack ?? null;
}

function participantVideoTrack(participant: RemoteParticipant | LocalParticipant): MediaStreamTrack | null {
  for (const publication of participant.trackPublications.values()) {
    if (publication.kind !== Track.Kind.Video) {
      continue;
    }
    const mediaTrack = publicationMediaTrack(publication);
    if (mediaTrack) {
      return mediaTrack;
    }
  }
  return null;
}

function participantMediaTracks(participant: RemoteParticipant | LocalParticipant): MediaStreamTrack[] {
  const tracks: MediaStreamTrack[] = [];
  for (const publication of participant.trackPublications.values()) {
    const mediaTrack = publicationMediaTrack(publication);
    if (mediaTrack) {
      tracks.push(mediaTrack);
    }
  }
  return tracks;
}

function publicationAudioTrack(publication: TrackPublication): MediaStreamTrack | null {
  const track = publication.track;
  if (!track) {
    return null;
  }
  if (track instanceof MediaStreamTrack) {
    return track;
  }
  const mediaTrack = (track as Track).mediaStreamTrack;
  return mediaTrack ?? null;
}

function participantAudioTracks(participant: RemoteParticipant | LocalParticipant): MediaStreamTrack[] {
  const tracks: MediaStreamTrack[] = [];
  for (const publication of participant.audioTrackPublications.values()) {
    const mediaTrack = publicationAudioTrack(publication);
    if (mediaTrack) {
      tracks.push(mediaTrack);
    }
  }
  return tracks;
}

/**
 * LiveKit implementation of the VideoService interface.
 */
export class LiveKitService extends VideoService {
  private room: Room | null = null;
  private localParticipant: LocalParticipant | null = null;
  private initialized = false;
  private connectionState: string = 'disconnected';
  private error: Error | null = null;
  private roomListeners = new Set<() => void>();
  private connectGeneration = 0;

  private pendingToken?: string;
  private pendingUrl?: string;
  private activeRoomId?: string;
  private connectPromise: Promise<void> | null = null;
  private connectPromiseKey: string | null = null;
  private intentionalLeave = false;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private attachedAudioSids = new Set<string>();
  private attachedAudioElements = new Map<string, HTMLAudioElement>();

  onRoomChange(listener: () => void): () => void {
    this.roomListeners.add(listener);
    return () => this.roomListeners.delete(listener);
  }

  private notifyRoomChange(): void {
    for (const listener of this.roomListeners) {
      listener();
    }
  }

  private isActiveSession(generation: number, room: Room | null): room is Room {
    return generation === this.connectGeneration && room !== null;
  }

  isConnectedToRoom(roomId: string): boolean {
    return (
      Boolean(roomId) &&
      this.initialized &&
      this.activeRoomId === roomId &&
      this.room?.state === ConnectionState.Connected
    );
  }

  isJoiningOrConnected(roomId: string): boolean {
    return this.isActiveInRoom(roomId);
  }

  private isConnectingToRoom(roomId: string): boolean {
    return (
      Boolean(roomId) &&
      this.activeRoomId === roomId &&
      (this.connectionState === 'connecting' ||
        this.connectionState === 'reconnecting' ||
        this.room?.state === ConnectionState.Connecting ||
        this.room?.state === ConnectionState.Reconnecting)
    );
  }

  private isActiveInRoom(roomId: string): boolean {
    return this.isConnectedToRoom(roomId) || this.isConnectingToRoom(roomId);
  }

  private sessionKey(roomId?: string, token?: string): string {
    return `${roomId ?? ''}:${token ?? ''}`;
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private shouldAutoReconnect(reason?: DisconnectReason): boolean {
    if (this.intentionalLeave) {
      return false;
    }
    return (
      reason !== DisconnectReason.CLIENT_INITIATED &&
      reason !== DisconnectReason.DUPLICATE_IDENTITY &&
      reason !== DisconnectReason.PARTICIPANT_REMOVED &&
      reason !== DisconnectReason.ROOM_DELETED
    );
  }

  private scheduleReconnect(roomId: string | undefined): void {
    if (!this.pendingToken || !this.pendingUrl || this.intentionalLeave) {
      return;
    }
    if (this.reconnectAttempts >= 5) {
      this.error = new Error('Connection lost. Close and rejoin the call.');
      this.connectionState = 'failed';
      this.notifyRoomChange();
      return;
    }

    this.clearReconnectTimer();
    const delayMs = Math.min(1000 * 2 ** this.reconnectAttempts, 8000);
    this.reconnectAttempts += 1;
    this.connectionState = 'reconnecting';
    this.notifyRoomChange();

    this.reconnectTimer = setTimeout(() => {
      if (this.intentionalLeave || !this.pendingToken) {
        return;
      }
      const generation = ++this.connectGeneration;
      void this.connectToRoom(generation, this.pendingToken, this.pendingUrl, roomId).catch(() => undefined);
    }, delayMs);
  }

  private attachRemoteAudioTrack(track: RemoteTrack): void {
    if (track.kind !== Track.Kind.Audio || this.attachedAudioSids.has(track.sid ?? '')) {
      return;
    }
    const element = track.attach();
    if (element instanceof HTMLAudioElement) {
      element.className = 'video-audio-track';
      element.volume = 1;
      this.attachedAudioElements.set(track.sid ?? '', element);
      void element.play().catch((err) => console.warn('Remote audio play blocked', err));
      this.attachedAudioSids.add(track.sid ?? '');
    }
  }

  private attachExistingRemoteAudio(room: Room): void {
    for (const [, participant] of room.remoteParticipants) {
      for (const publication of participant.audioTrackPublications.values()) {
        const track = publication.track;
        if (track instanceof RemoteTrack) {
          this.attachRemoteAudioTrack(track);
        }
      }
    }
  }

  private detachAllRemoteAudio(): void {
    for (const track of this.attachedAudioElements.keys()) {
      const element = this.attachedAudioElements.get(track);
      element?.pause();
    }
    if (this.room) {
      for (const sid of this.attachedAudioSids) {
        for (const [, participant] of this.room.remoteParticipants) {
          for (const publication of participant.audioTrackPublications.values()) {
            if (publication.trackSid === sid && publication.track instanceof RemoteTrack) {
              publication.track.detach();
            }
          }
        }
      }
    }
    this.attachedAudioElements.clear();
    this.attachedAudioSids.clear();
  }

  async ensureAudioPlayback(): Promise<void> {
    if (!this.room) {
      return;
    }
    try {
      await this.room.startAudio();
    } catch (err) {
      console.warn('Could not start room audio playback', err);
    }
    for (const element of this.attachedAudioElements.values()) {
      void element.play().catch(() => undefined);
    }
    this.attachExistingRemoteAudio(this.room);
  }

  getLocalMediaState(): { micEnabled: boolean; cameraEnabled: boolean } {
    return {
      micEnabled: this.localParticipant?.isMicrophoneEnabled ?? true,
      cameraEnabled: this.localParticipant?.isCameraEnabled ?? false,
    };
  }

  private attachRoomListeners(room: Room, generation: number): void {
    const notify = () => this.notifyRoomChange();

    room.on(RoomEvent.TrackSubscribed, (track, _publication, participant) => {
      if (this.room !== room || participant.isLocal) {
        return;
      }
      if (track instanceof RemoteTrack && track.kind === Track.Kind.Audio) {
        this.attachRemoteAudioTrack(track);
      }
      notify();
    });
    room.on(RoomEvent.TrackUnsubscribed, (track) => {
      if (this.room !== room) {
        return;
      }
      if (track instanceof RemoteTrack && track.kind === Track.Kind.Audio) {
        track.detach();
        this.attachedAudioSids.delete(track.sid ?? '');
        this.attachedAudioElements.delete(track.sid ?? '');
      }
      notify();
    });
    room.on('connected', () => {
      if (!this.isActiveSession(generation, this.room) || this.room !== room) {
        return;
      }
      this.connectionState = 'connected';
      this.error = null;
      this.localParticipant = room.localParticipant ?? null;
      this.attachExistingRemoteAudio(room);
      notify();
    });
    room.on('disconnected', (reason) => {
      if (this.room !== room) {
        return;
      }
      this.connectionState = 'disconnected';
      this.localParticipant = null;
      this.initialized = false;

      if (reason === DisconnectReason.DUPLICATE_IDENTITY) {
        this.error = new Error(
          'Disconnected: you joined this call from another tab or window. Close the other session and rejoin.',
        );
        this.connectionState = 'failed';
      } else if (!this.shouldAutoReconnect(reason)) {
        this.error = null;
      }

      notify();

      if (this.shouldAutoReconnect(reason)) {
        this.scheduleReconnect(this.activeRoomId);
      }
    });
    room.on('reconnecting', () => {
      if (this.room !== room) {
        return;
      }
      this.connectionState = 'reconnecting';
      notify();
    });
    room.on('connectionStateChanged', (state) => {
      if (this.room !== room) {
        return;
      }
      this.connectionState = String(state);
      notify();
    });
    room.on('participantConnected', notify);
    room.on('participantDisconnected', notify);
    room.on('trackSubscribed', notify);
    room.on('trackUnsubscribed', notify);
    room.on('trackMuted', notify);
    room.on('trackUnmuted', notify);
    room.on('localTrackPublished', notify);
    room.on('localTrackUnpublished', notify);
  }

  private async enableDefaultDevices(participant: LocalParticipant, generation: number): Promise<void> {
    await participant.setMicrophoneEnabled(true);
    if (!this.isActiveSession(generation, this.room)) {
      return;
    }
    await participant.setCameraEnabled(false);
  }

  async initialize(token: string, url?: string, roomId?: string): Promise<void> {
    this.pendingToken = token;
    if (url?.trim()) {
      this.pendingUrl = url;
    }

    if (roomId && this.isConnectedToRoom(roomId)) {
      return;
    }

    const key = this.sessionKey(roomId, token);
    if (this.connectPromise && this.connectPromiseKey === key) {
      return this.connectPromise;
    }

    if (roomId && this.isConnectingToRoom(roomId)) {
      return this.connectPromise ?? Promise.resolve();
    }

    const generation = ++this.connectGeneration;
    this.intentionalLeave = false;
    this.clearReconnectTimer();

    this.connectPromiseKey = key;
    this.connectPromise = this.connectToRoom(generation, token, url, roomId);
    try {
      await this.connectPromise;
    } finally {
      if (this.connectPromiseKey === key) {
        this.connectPromise = null;
        this.connectPromiseKey = null;
      }
    }
  }

  private async connectToRoom(
    generation: number,
    token: string,
    url: string | undefined,
    roomId: string | undefined,
  ): Promise<void> {
    await this.leaveRoomInternal(false);

    this.pendingToken = token;
    this.pendingUrl =
      url ?? (import.meta as ImportMeta & { env?: Record<string, string> }).env?.VITE_LIVEKIT_URL ?? '';
    this.activeRoomId = roomId;

    if (!this.pendingUrl?.trim()) {
      const err = new Error('LiveKit URL is missing. Set LIVEKIT_URL on the API or VITE_LIVEKIT_URL in the frontend.');
      this.error = err;
      this.connectionState = 'failed';
      throw err;
    }

    const room = new Room();
    this.room = room;
    this.attachRoomListeners(room, generation);

    try {
      this.connectionState = 'connecting';
      await room.connect(this.pendingUrl, this.pendingToken);

      if (!this.isActiveSession(generation, this.room)) {
        return;
      }

      const participant = this.room.localParticipant;
      if (!participant) {
        throw new Error('Connected to LiveKit but local participant is unavailable.');
      }

      this.localParticipant = participant;
      await this.enableDefaultDevices(participant, generation);

      if (!this.isActiveSession(generation, this.room)) {
        return;
      }

      try {
        await room.startAudio();
      } catch (err) {
        console.warn('Could not start room audio playback', err);
      }

      this.attachExistingRemoteAudio(room);

      this.initialized = true;
      this.connectionState = 'connected';
      this.activeRoomId = roomId || room.name;
      this.reconnectAttempts = 0;
      this.error = null;
      this.notifyRoomChange();
    } catch (err) {
      if (generation === this.connectGeneration) {
        this.error = err instanceof Error ? err : new Error(String(err));
        this.connectionState = 'failed';
        this.initialized = false;
        this.localParticipant = null;
        await this.leaveRoomInternal(true);
      }
      throw err;
    }
  }

  async joinRoom(): Promise<void> {
    if (!this.room) {
      throw new Error('LiveKitService not initialized');
    }
    if (this.room.state === ConnectionState.Connected) {
      return;
    }
    if (!this.pendingToken || !this.pendingUrl) {
      throw new Error('Missing LiveKit credentials');
    }
    await this.room.connect(this.pendingUrl, this.pendingToken);
    this.localParticipant = this.room.localParticipant ?? null;
    this.notifyRoomChange();
  }

  private async leaveRoomInternal(invalidateSession = true): Promise<void> {
    this.clearReconnectTimer();
    if (invalidateSession) {
      this.connectGeneration += 1;
      this.connectPromise = null;
      this.connectPromiseKey = null;
    }
    const room = this.room;
    this.detachAllRemoteAudio();
    this.room = null;
    this.localParticipant = null;
    this.initialized = false;
    this.activeRoomId = undefined;
    this.connectionState = 'disconnected';
    this.error = null;

    if (room) {
      room.removeAllListeners();
      try {
        await room.disconnect();
      } catch {
        // ignore disconnect errors during cleanup
      }
    }
    this.notifyRoomChange();
  }

  async leaveRoom(): Promise<void> {
    this.intentionalLeave = true;
    this.clearReconnectTimer();
    this.connectPromise = null;
    this.connectPromiseKey = null;
    this.pendingToken = undefined;
    this.pendingUrl = undefined;
    await this.leaveRoomInternal();
  }

  async getLocalTracks(): Promise<MediaStreamTrack[]> {
    if (!this.localParticipant) {
      return [];
    }
    const videoTrack = participantVideoTrack(this.localParticipant);
    return videoTrack ? [videoTrack] : [];
  }

  async publishTrack(track: MediaStreamTrack): Promise<void> {
    if (!this.localParticipant) {
      throw new Error('Not connected to a room');
    }
    await this.localParticipant.publishTrack(track);
    this.notifyRoomChange();
  }

  async unpublishTrack(track: MediaStreamTrack): Promise<void> {
    if (!this.localParticipant) {
      throw new Error('Not connected to a room');
    }
    await this.localParticipant.unpublishTrack(track);
    this.notifyRoomChange();
  }

  async setAudioEnabled(enabled: boolean): Promise<void> {
    if (!this.localParticipant) {
      throw new Error('Not connected to a room');
    }
    await this.localParticipant.setMicrophoneEnabled(enabled);
    this.notifyRoomChange();
  }

  async setVideoEnabled(enabled: boolean): Promise<void> {
    if (!this.localParticipant) {
      throw new Error('Not connected to a room');
    }
    await this.localParticipant.setCameraEnabled(enabled);
    this.notifyRoomChange();
  }

  async shareScreen(): Promise<void> {
    if (!this.localParticipant) {
      throw new Error('Not connected to a room');
    }
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: false,
    });
    const videoTrack = stream.getVideoTracks()[0];
    if (!videoTrack) {
      throw new Error('No video track from screen share');
    }
    await this.localParticipant.publishTrack(videoTrack);
    videoTrack.onended = () => {
      this.stopShareScreen().catch(console.error);
    };
    this.notifyRoomChange();
  }

  async stopShareScreen(): Promise<void> {
    if (!this.localParticipant) {
      return;
    }
    const tracks = await this.getLocalTracks();
    for (const track of tracks) {
      if (track.kind === 'video') {
        await this.localParticipant.unpublishTrack(track);
      }
    }
    this.notifyRoomChange();
  }

  async sendData(data: Uint8Array | string): Promise<void> {
    if (!this.localParticipant) {
      throw new Error('Not connected to a room');
    }
    await this.localParticipant.publishData(data, { reliable: true });
  }

  getRoom(): Room | null {
    return this.room;
  }

  async getRemoteParticipants(): Promise<ParticipantInfo[]> {
    if (!this.room) {
      return [];
    }
    const participants: ParticipantInfo[] = [];
    for (const [, participant] of this.room.remoteParticipants) {
      let meta: unknown = undefined;
      if (typeof participant.metadata === 'string') {
        try {
          meta = JSON.parse(participant.metadata);
        } catch {
          meta = participant.metadata;
        }
      } else {
        meta = participant.metadata;
      }
      participants.push({
        participant_id: participant.identity,
        name: participant.name || participant.identity,
        role:
          typeof meta === 'object' && meta !== null && 'role' in meta
            ? (meta as { role?: string }).role ?? ''
            : '',
        metadata: meta as Record<string, unknown> | null,
      });
    }
    return participants;
  }

  async getParticipantTracks(participantId: string): Promise<MediaStreamTrack[]> {
    if (!this.room) {
      return [];
    }
    const participant = this.room.remoteParticipants.get(participantId);
    if (!participant) {
      return [];
    }
    return participantMediaTracks(participant);
  }

  async getParticipantAudioTracks(participantId: string): Promise<MediaStreamTrack[]> {
    if (!this.room) {
      return [];
    }
    const participant = this.room.remoteParticipants.get(participantId);
    if (!participant) {
      return [];
    }
    return participantAudioTracks(participant);
  }

  getAudioStatus(): { participant_id: string; label: string; mic_active: boolean; is_local: boolean }[] {
    const items: { participant_id: string; label: string; mic_active: boolean; is_local: boolean }[] = [];
    if (this.localParticipant) {
      items.push({
        participant_id: this.localParticipant.identity,
        label: 'You',
        mic_active: this.localParticipant.isMicrophoneEnabled,
        is_local: true,
      });
    }
    if (this.room) {
      for (const [, participant] of this.room.remoteParticipants) {
        items.push({
          participant_id: participant.identity,
          label: participant.name || participant.identity,
          mic_active: participant.isMicrophoneEnabled,
          is_local: false,
        });
      }
    }
    return items;
  }

  getConnectionState(): string {
    return this.connectionState;
  }

  getError(): Error | null {
    return this.error;
  }
}
