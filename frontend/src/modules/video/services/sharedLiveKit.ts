import { LiveKitService } from './livekitService';

/** One LiveKit client per browser tab — survives React StrictMode remounts. */
let sharedService: LiveKitService | null = null;

export function getSharedLiveKitService(): LiveKitService {
  if (!sharedService) {
    sharedService = new LiveKitService();
  }
  return sharedService;
}

export async function releaseSharedLiveKitService(): Promise<void> {
  if (!sharedService) {
    return;
  }
  await sharedService.leaveRoom();
  sharedService = null;
}
