import { useCallback } from 'react';
import { useVideoControls } from '../hooks/useVideoControls';
import { VideoControlButton } from './VideoControlButton';

export const MicToggle = () => {
  const { toggleAudio, localMedia, ensureAudioPlayback } = useVideoControls();
  const micOn = localMedia.micEnabled;

  const handleClick = useCallback(async () => {
    await ensureAudioPlayback();
    await toggleAudio();
  }, [ensureAudioPlayback, toggleAudio]);

  return (
    <VideoControlButton
      icon={micOn ? 'mic' : 'mic_off'}
      label={micOn ? 'Mute microphone' : 'Unmute microphone'}
      active={micOn}
      onClick={() => void handleClick()}
    />
  );
};
