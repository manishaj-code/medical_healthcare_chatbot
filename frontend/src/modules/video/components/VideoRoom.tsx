import { PropsWithChildren } from 'react';
import { useVideoRoom } from '../hooks/useVideoRoom';
import { ParticipantGrid } from './ParticipantGrid';
import { VideoControls } from './VideoControls';
import { RemoteAudioPlayback } from './RemoteAudioPlayback';
import { AudioStatusBar } from './AudioStatusBar';
import { AudioUnlockBanner } from './AudioUnlockBanner';

interface VideoRoomProps extends PropsWithChildren<{
  /** Token obtained from backend (required) */
  token: string;
  /** LiveKit URL (optional; can be set via env or provider) */
  url?: string;
  /** Automatically join when token changes */
  autoJoin?: boolean;
  /** Callback when user leaves the room */
  onLeave?: () => void;
  /** Show local preview in the grid */
  showLocalPreview?: boolean;
  /** Use compact layout for modal embedding */
  compact?: boolean;
  /** Who the local participant is waiting for once connected */
  waitingFor?: "doctor" | "patient";
}> {}

/**
 * Main video room component.
 * Must be used within a VideoProvider that supplies the token and url,
 * or you can wrap it with VideoProvider inline.
 */
export const VideoRoom = ({
  children,
  token,
  url,
  autoJoin = true,
  onLeave,
  showLocalPreview = true,
  compact = false,
  waitingFor = "doctor",
}: VideoRoomProps) => {
  const { connectionState, error, remoteParticipants } = useVideoRoom();

  return (
    <div className={compact ? "video-room video-room--compact" : "video-room"}>
      <div className="video-room-header">
        <div>
          <h3>Video Consultation</h3>
          {connectionState === "connected" && remoteParticipants.length === 0 && (
            <p className="video-room-status">
              Connected — waiting for {waitingFor} to join
            </p>
          )}
          {connectionState === "connected" && remoteParticipants.length > 0 && (
            <p className="video-room-status">
              In call with {remoteParticipants.map((p) => p.name || p.participant_id).join(", ")}
            </p>
          )}
          {connectionState === "connecting" && (
            <p className="video-room-status">Connecting to LiveKit…</p>
          )}
          {connectionState === "reconnecting" && (
            <p className="video-room-status">Reconnecting…</p>
          )}
        </div>
      </div>

      <div className="video-room-stage">
        <RemoteAudioPlayback />
        <AudioUnlockBanner />
        {connectionState === "failed" && error && (
          <div className="video-room-error">
            <p>Connection failed: {error.message}</p>
          </div>
        )}
        {connectionState !== "failed" && (
          <ParticipantGrid showLocalPreview={showLocalPreview} waitingFor={waitingFor} />
        )}
      </div>

      <div className="video-room-controls">
        <AudioStatusBar />
        <VideoControls onLeave={onLeave} />
        {children}
      </div>
    </div>
  );
};