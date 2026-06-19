import { useCallback } from 'react';
import { useVideoControls } from '../hooks/useVideoControls';
import { VideoControlButton } from './VideoControlButton';

export const CameraToggle = () => {
  const { toggleVideo, localMedia, ensureAudioPlayback } = useVideoControls();
  const cameraOn = localMedia.cameraEnabled;

  const handleClick = useCallback(async () => {
    await ensureAudioPlayback();
    await toggleVideo();
  }, [ensureAudioPlayback, toggleVideo]);

  return (
    <VideoControlButton
      icon={cameraOn ? 'videocam' : 'videocam_off'}
      label={cameraOn ? 'Turn off camera' : 'Turn on camera'}
      active={cameraOn}
      onClick={() => void handleClick()}
    />
  );
};
