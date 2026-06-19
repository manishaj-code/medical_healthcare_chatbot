import { useCallback, useEffect, useState } from 'react';
import { useVideoRoom } from '../hooks/useVideoRoom';
import { LiveKitService } from '../services/livekitService';

export const AudioUnlockBanner = () => {
  const { service, connectionState, remoteParticipants } = useVideoRoom();
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (remoteParticipants.length === 0) {
      setDismissed(false);
    }
  }, [remoteParticipants.length]);

  const unlock = useCallback(async () => {
    if (service instanceof LiveKitService) {
      await service.ensureAudioPlayback();
    }
    setDismissed(true);
  }, [service]);

  if (dismissed || connectionState !== 'connected' || remoteParticipants.length === 0) {
    return null;
  }

  return (
    <button type="button" className="video-audio-unlock" onClick={() => void unlock()}>
      <span className="material-symbols-outlined">volume_up</span>
      Tap to hear the other participant
    </button>
  );
};
