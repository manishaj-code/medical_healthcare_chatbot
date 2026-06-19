import { useVideoRoom } from '../hooks/useVideoRoom';

export const AudioStatusBar = () => {
  const { audioStatus } = useVideoRoom();

  if (!audioStatus.length) {
    return null;
  }

  return (
    <div className="video-audio-status" aria-live="polite">
      {audioStatus.map((item) => (
        <span
          key={item.participant_id}
          className={`video-audio-status-chip${item.mic_active ? ' video-audio-status-chip--on' : ' video-audio-status-chip--off'}`}
        >
          <span className="material-symbols-outlined" aria-hidden>
            {item.mic_active ? 'mic' : 'mic_off'}
          </span>
          {item.label}: {item.mic_active ? 'Mic on — audio active' : 'Mic muted'}
        </span>
      ))}
    </div>
  );
};
