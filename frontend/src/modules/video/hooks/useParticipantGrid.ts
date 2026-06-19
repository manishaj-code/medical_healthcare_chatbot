import { useVideoRoom } from './useVideoRoom';
import type { ParticipantInfo } from '../types';

/**
 * Hook that returns the list of remote participants.
 * Useful for rendering a grid of video feeds.
 */
export function useParticipantGrid(): ParticipantInfo[] {
  const { remoteParticipants } = useVideoRoom();
  return remoteParticipants;
}