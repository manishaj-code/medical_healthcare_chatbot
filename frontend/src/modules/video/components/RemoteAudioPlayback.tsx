import { useEffect, useState } from 'react';
import { useVideoRoom } from '../hooks/useVideoRoom';
import { AudioTrack } from './AudioTrack';

/** Fallback audio elements when LiveKit attach() is unavailable. */
export const RemoteAudioPlayback = () => {
  const { service, remoteParticipants, connectionState, audioStatus } = useVideoRoom();
  const [audioTracks, setAudioTracks] = useState<{ key: string; track: MediaStreamTrack }[]>([]);

  useEffect(() => {
    if (connectionState !== 'connected') {
      setAudioTracks([]);
      return;
    }

    const load = async () => {
      const next: { key: string; track: MediaStreamTrack }[] = [];
      for (const participant of remoteParticipants) {
        const tracks = await service.getParticipantAudioTracks(participant.participant_id);
        tracks.forEach((track) => {
          next.push({
            key: `${participant.participant_id}-${track.id}`,
            track,
          });
        });
      }
      setAudioTracks(next);
    };

    void load();
  }, [remoteParticipants, service, connectionState, audioStatus]);

  return (
    <>
      {audioTracks.map(({ key, track }) => (
        <AudioTrack key={key} track={track} />
      ))}
    </>
  );
};
