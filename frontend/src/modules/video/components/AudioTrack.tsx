import { useEffect, useRef } from 'react';

interface AudioTrackProps {
  track: MediaStreamTrack;
}

/** Plays a remote (or local monitor) audio track. Hidden from view. */
export const AudioTrack = ({ track }: AudioTrackProps) => {
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const stream = new MediaStream([track]);
    audio.srcObject = stream;
    audio.muted = false;
    audio.volume = 1;

    const playPromise = audio.play();
    if (playPromise !== undefined) {
      playPromise.catch((err) => console.warn('Audio play failed', err));
    }

    return () => {
      audio.srcObject = null;
    };
  }, [track]);

  return <audio ref={audioRef} autoPlay playsInline className="video-audio-track" />;
};
