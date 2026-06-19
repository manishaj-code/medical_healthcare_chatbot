import { useEffect, useState } from 'react';
import { useVideoRoom } from '../hooks/useVideoRoom';
import type { ParticipantInfo } from '../types';
import { VideoTrack } from './VideoTrack';

interface ParticipantGridProps {
  showLocalPreview?: boolean;
  waitingFor?: 'doctor' | 'patient';
}

function participantLabel(participant: ParticipantInfo): string {
  return participant.name || participant.participant_id;
}

export const ParticipantGrid = ({
  showLocalPreview = true,
  waitingFor = 'doctor',
}: ParticipantGridProps) => {
  const { service, remoteParticipants, localTracks } = useVideoRoom();
  const [participantTracks, setParticipantTracks] = useState<Record<string, MediaStreamTrack[]>>({});

  useEffect(() => {
    const fetchTracks = async () => {
      const newMap: Record<string, MediaStreamTrack[]> = {};
      for (const participant of remoteParticipants) {
        try {
          const tracks = await service.getParticipantTracks(participant.participant_id);
          newMap[participant.participant_id] = tracks.filter((track) => track.kind === 'video');
        } catch (e) {
          console.warn(`Failed to get tracks for ${participant.participant_id}`, e);
          newMap[participant.participant_id] = [];
        }
      }
      setParticipantTracks(newMap);
    };
    if (service) {
      void fetchTracks();
    }
  }, [remoteParticipants, service]);

  const localVideoTracks = localTracks.filter((track) => track.kind === 'video');
  const waitingLabel = waitingFor === 'doctor' ? 'doctor' : 'patient';

  return (
    <div className="participant-grid">
      {showLocalPreview && (
        <div className="participant-grid-tile">
          <h4>You</h4>
          {localVideoTracks.length > 0 ? (
            localVideoTracks.map((track, idx) => (
              <div key={idx} className="participant-grid-track">
                <VideoTrack track={track} label="You (local)" isLocal />
              </div>
            ))
          ) : (
            <p className="participant-grid-wait">Camera off — tap the camera control to enable</p>
          )}
        </div>
      )}

      {remoteParticipants.length === 0 && (
        <div className="participant-grid-tile participant-grid-tile--waiting">
          <p className="participant-grid-wait">Waiting for {waitingLabel} to join…</p>
        </div>
      )}

      {remoteParticipants.map((participant) => {
        const tracks = participantTracks[participant.participant_id] ?? [];
        const displayName = participantLabel(participant);
        return (
          <div key={participant.participant_id} className="participant-grid-tile">
            <h4>{displayName}</h4>
            {tracks.length === 0 ? (
              <p className="participant-grid-wait">
                {displayName} is connected — camera off or mic only
              </p>
            ) : (
              tracks.map((track, idx) => (
                <div key={idx} className="participant-grid-track">
                  <VideoTrack track={track} label={displayName} />
                </div>
              ))
            )}
          </div>
        );
      })}
    </div>
  );
};
