import { useCallback, useState } from 'react';
import { useVideoControls } from '../hooks/useVideoControls';
import { VideoControlButton } from './VideoControlButton';

export const ScreenShareToggle = () => {
  const { shareScreen, stopShareScreen } = useVideoControls();
  const [sharing, setSharing] = useState(false);

  const handleClick = useCallback(async () => {
    try {
      if (sharing) {
        await stopShareScreen();
        setSharing(false);
      } else {
        await shareScreen();
        setSharing(true);
      }
    } catch (e) {
      console.error('Screen share failed', e);
    }
  }, [shareScreen, sharing, stopShareScreen]);

  return (
    <VideoControlButton
      icon={sharing ? 'stop_screen_share' : 'present_to_all'}
      label={sharing ? 'Stop screen share' : 'Share screen'}
      active={sharing}
      onClick={() => void handleClick()}
    />
  );
};
