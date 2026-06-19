import { PropsWithChildren, useEffect, useRef } from 'react';
import { VideoContext } from './VideoContext';
import type { VideoService } from '../interfaces/videoService';
import { LiveKitService } from '../services/livekitService';

type VideoProviderProps = PropsWithChildren<{
  service?: VideoService;
  token?: string;
  url?: string;
  roomId?: string;
  autoJoin?: boolean;
}>;

export const VideoProvider = ({
  children,
  service: providedService,
  token,
  url,
  roomId,
  autoJoin = true,
}: VideoProviderProps) => {
  const serviceRef = useRef<VideoService | null>(null);

  if (!serviceRef.current) {
    serviceRef.current = providedService ?? new LiveKitService();
  }
  const service = serviceRef.current;

  useEffect(() => {
    if (!token || !autoJoin) {
      return undefined;
    }

    let cancelled = false;

    (async () => {
      try {
        if (service instanceof LiveKitService && roomId && service.isJoiningOrConnected(roomId)) {
          return;
        }
        await service.initialize(token, url, roomId);
        if (cancelled) {
          console.warn('Video room initialized after provider unmounted');
        }
      } catch (err) {
        if (!cancelled) {
          console.error('Failed to initialize video room', err);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [token, url, roomId, autoJoin, service]);

  return (
    <VideoContext.Provider value={service}>
      {children}
    </VideoContext.Provider>
  );
};
