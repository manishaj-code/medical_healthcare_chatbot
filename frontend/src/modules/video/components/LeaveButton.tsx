import { useCallback } from 'react';
import { useVideoControls } from '../hooks/useVideoControls';
import { VideoControlButton } from './VideoControlButton';

export const LeaveButton = ({ onLeave }: { onLeave?: () => void }) => {
  const { leaveRoom } = useVideoControls();

  const handleClick = useCallback(async () => {
    await leaveRoom();
    onLeave?.();
  }, [leaveRoom, onLeave]);

  return (
    <VideoControlButton
      icon="call_end"
      label="Leave call"
      active
      danger
      wide
      onClick={() => void handleClick()}
    >
      <span className="video-control-btn-label">Leave</span>
    </VideoControlButton>
  );
};
