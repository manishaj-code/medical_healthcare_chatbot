import { createContext, useContext } from 'react';
import type { VideoService } from '../interfaces/videoService';

export const VideoContext = createContext<VideoService | null>(null);

export const useVideoContext = () => {
  const ctx = useContext(VideoContext);
  if (!ctx) {
    throw new Error('useVideoContext must be used within a VideoProvider');
  }
  return ctx;
};