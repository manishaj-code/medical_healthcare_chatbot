/** Prevents duplicate toasts when chat/UI already showed one and poll picks up the same backend notification. */

const SUPPRESS_MS = 20_000;
const shownAt = new Map<string, number>();

function prune(now: number) {
  for (const [key, at] of shownAt) {
    if (now - at > SUPPRESS_MS) shownAt.delete(key);
  }
}

export function markNotificationToastShown(type: string, title?: string) {
  const now = Date.now();
  shownAt.set(`type:${type}`, now);
  if (title) shownAt.set(`title:${title.toLowerCase()}`, now);
}

export function isNotificationToastSuppressed(type: string, title?: string): boolean {
  const now = Date.now();
  prune(now);
  const typeAt = shownAt.get(`type:${type}`);
  if (typeAt != null && now - typeAt < SUPPRESS_MS) return true;
  if (title) {
    const titleAt = shownAt.get(`title:${title.toLowerCase()}`);
    if (titleAt != null && now - titleAt < SUPPRESS_MS) return true;
  }
  return false;
}
