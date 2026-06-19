import { useVideoRoom } from './useVideoRoom';

export function useVideoControls() {
  const {
    toggleAudio,
    toggleVideo,
    leaveRoom,
    shareScreen,
    stopShareScreen,
    sendData,
    connectionState,
    error,
    audioStatus,
    localMedia,
    ensureAudioPlayback,
  } = useVideoRoom();

  return {
    toggleAudio,
    toggleVideo,
    leaveRoom,
    shareScreen,
    stopShareScreen,
    sendData,
    connectionState,
    error,
    audioStatus,
    localMedia,
    ensureAudioPlayback,
  };
}
