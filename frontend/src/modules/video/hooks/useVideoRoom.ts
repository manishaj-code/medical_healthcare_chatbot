import { useCallback, useEffect, useRef, useState } from 'react';
import { useVideoContext } from '../context/VideoContext';
import type { VideoService } from '../interfaces/videoService';
import type { ParticipantInfo } from '../types';
import { LiveKitService } from '../services/livekitService';
import { useInterval } from './useInterval';

export interface UseVideoRoomReturn {
  service: VideoService;
  connectionState: string;
  error: Error | null;
  localTracks: MediaStreamTrack[];
  remoteParticipants: ParticipantInfo[];
  audioStatus: { participant_id: string; label: string; mic_active: boolean; is_local: boolean }[];
  initialize: (token: string, url?: string) => Promise<void>;
  joinRoom: () => Promise<void>;
  leaveRoom: () => Promise<void>;
  toggleAudio: () => Promise<void>;
  toggleVideo: () => Promise<void>;
  shareScreen: () => Promise<void>;
  stopShareScreen: () => Promise<void>;
  sendData: (data: Uint8Array | string) => Promise<void>;
}

async function refreshRoomState(service: VideoService) {
  const [localTracks, remoteParticipants] = await Promise.all([
    service.getLocalTracks(),
    service.getRemoteParticipants(),
  ]);
  return {
    connectionState: service.getConnectionState(),
    error: service.getError(),
    localTracks,
    remoteParticipants,
    audioStatus: service.getAudioStatus(),
  };
}

export function useVideoRoom(): UseVideoRoomReturn {
  const service = useVideoContext();
  const [connectionState, setConnectionState] = useState<string>('disconnected');
  const [error, setError] = useState<Error | null>(null);
  const [localTracks, setLocalTracks] = useState<MediaStreamTrack[]>([]);
  const [remoteParticipants, setRemoteParticipants] = useState<ParticipantInfo[]>([]);
  const [audioStatus, setAudioStatus] = useState<
    { participant_id: string; label: string; mic_active: boolean; is_local: boolean }[]
  >([]);
  const [localMedia, setLocalMedia] = useState({ micEnabled: true, cameraEnabled: false });
  const [roomVersion, setRoomVersion] = useState(0);

  const syncState = useCallback(async () => {
    try {
      const next = await refreshRoomState(service);
      setConnectionState(next.connectionState);
      setError(next.error);
      setLocalTracks(next.localTracks);
      setRemoteParticipants(next.remoteParticipants);
      setAudioStatus(next.audioStatus);
      const media = service.getLocalMediaState();
      setLocalMedia(media);
      audioEnabledRef.current = media.micEnabled;
      videoEnabledRef.current = media.cameraEnabled;
    } catch {
      // ignore transient read errors
    }
  }, [service]);

  useEffect(() => {
    void syncState();
  }, [syncState, roomVersion]);

  useEffect(() => {
    if (service instanceof LiveKitService) {
      return service.onRoomChange(() => {
        setRoomVersion((v) => v + 1);
      });
    }
    return undefined;
  }, [service]);

  useInterval(() => {
    void syncState();
  }, 1000);

  const initialize = useCallback(
    async (token: string, url?: string) => {
      await service.initialize(token, url);
      setRoomVersion((v) => v + 1);
    },
    [service],
  );

  const joinRoom = useCallback(async () => {
    await service.joinRoom();
    setRoomVersion((v) => v + 1);
  }, [service]);

  const leaveRoom = useCallback(async () => {
    await service.leaveRoom();
    setRoomVersion((v) => v + 1);
  }, [service]);

  const audioEnabledRef = useRef<boolean>(true);
  const videoEnabledRef = useRef<boolean>(false);

  const toggleAudioSafe = useCallback(async () => {
    const next = !audioEnabledRef.current;
    await service.setAudioEnabled(next);
    audioEnabledRef.current = next;
    setLocalMedia(service.getLocalMediaState());
    setRoomVersion((v) => v + 1);
  }, [service]);

  const toggleVideoSafe = useCallback(async () => {
    const next = !videoEnabledRef.current;
    await service.setVideoEnabled(next);
    videoEnabledRef.current = next;
    setLocalMedia(service.getLocalMediaState());
    setRoomVersion((v) => v + 1);
  }, [service]);

  const shareScreen = useCallback(async () => {
    await service.shareScreen();
    setRoomVersion((v) => v + 1);
  }, [service]);

  const stopShareScreen = useCallback(async () => {
    await service.stopShareScreen();
    setRoomVersion((v) => v + 1);
  }, [service]);

  const sendData = useCallback(
    async (data: Uint8Array | string) => {
      await service.sendData(data);
    },
    [service],
  );

  const ensureAudioPlayback = useCallback(async () => {
    await service.ensureAudioPlayback();
  }, [service]);

  return {
    service,
    connectionState,
    error,
    localTracks,
    remoteParticipants,
    audioStatus,
    localMedia,
    ensureAudioPlayback,
    initialize,
    joinRoom,
    leaveRoom,
    toggleAudio: toggleAudioSafe,
    toggleVideo: toggleVideoSafe,
    shareScreen,
    stopShareScreen,
    sendData,
  };
}
