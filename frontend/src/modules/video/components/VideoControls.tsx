import { useVideoControls } from '../hooks/useVideoControls';
import { MicToggle } from './MicToggle';
import { CameraToggle } from './CameraToggle';
import { LeaveButton } from './LeaveButton';
import { ScreenShareToggle } from './ScreenShareToggle';

interface VideoControlsProps {
  onLeave?: () => void;
}

export const VideoControls = ({ onLeave }: VideoControlsProps) => {
  const { connectionState, error } = useVideoControls();

  const statusLabel =
    connectionState === 'connected'
      ? 'Connected'
      : connectionState === 'connecting'
        ? 'Connecting'
        : connectionState === 'reconnecting'
          ? 'Reconnecting'
          : connectionState === 'failed'
            ? 'Failed'
            : 'Disconnected';

  const statusClass =
    connectionState === 'connected'
      ? 'video-control-status--ok'
      : connectionState === 'failed'
        ? 'video-control-status--error'
        : 'video-control-status--pending';

  return (
    <div className="video-control-bar">
      <div className="video-control-bar-group">
        <MicToggle />
        <CameraToggle />
        <ScreenShareToggle />
      </div>

      <LeaveButton onLeave={onLeave} />

      <span className={`video-control-status ${statusClass}`} aria-live="polite">
        <span className="video-control-status-dot" aria-hidden />
        {statusLabel}
        {connectionState === 'failed' && error?.message ? ` — ${error.message}` : ''}
      </span>
    </div>
  );
};
