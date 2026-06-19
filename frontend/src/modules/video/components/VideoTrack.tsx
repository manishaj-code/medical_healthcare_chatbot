import { useEffect, useRef } from 'react';

interface VideoTrackProps {
  /** MediaStreamTrack to render (video track) */
  track: MediaStreamTrack;
  /** Optional label to display (e.g., participant name) */
  label?: string;
  /** Whether this is the local preview (usually muted) */
  isLocal?: boolean;
}

/**
 * Renders a video track inside a video element.
 * Handles attaching/detaching the track when the component mounts/unmounts.
 */
export const VideoTrack = ({ track, label, isLocal = false }: VideoTrackProps) => {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    // Create a MediaStream from the track and attach to video element
    const stream = new MediaStream([track]);
    video.srcObject = stream;
    video.muted = isLocal; // local preview should be muted to avoid echo
    video.playsInline = true;
    // Play the video (required for autoplay in most browsers)
    const playPromise = video.play();
    if (playPromise !== undefined) {
      playPromise.catch((err) => console.warn('Video play failed', err));
    }
    return () => {
      video.srcObject = null;
    };
  }, [track, isLocal]);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', background: '#000' }}>
      <video ref={videoRef} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
      {label && (
        <div
          style={{
            position: 'absolute',
            bottom: 8,
            left: 8,
            color: '#fff',
            fontSize: 14,
            background: 'rgba(0,0,0,0.4)',
            padding: '2px 6px',
            borderRadius: 4,
          }}
        >
          {label}
        </div>
      )}
    </div>
  );
};