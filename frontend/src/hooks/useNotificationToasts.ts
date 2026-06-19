import { useCallback, useEffect, useRef } from "react";
import { api } from "../api/client";
import { useToast } from "../components/toast/ToastProvider";
import { NotificationItem, getNotificationToastMeta } from "../utils/notifications";
import { NOTIFICATIONS_POLL_EVENT } from "../utils/notificationToast";
import { isNotificationToastSuppressed, markNotificationToastShown } from "../utils/toastSuppression";

const POLL_MS = 5_000;
const UNREAD_CHECK_MS = 3_000;

export function useNotificationToasts(apiPrefix: string) {
  const { showToast } = useToast();
  const seenIdsRef = useRef<Set<string>>(new Set());
  const initializedRef = useRef(false);
  const lastUnreadRef = useRef(0);

  const processNotifications = useCallback(
    (notes: NotificationItem[]) => {
      if (!initializedRef.current) {
        notes.forEach((n) => seenIdsRef.current.add(n.id));
        initializedRef.current = true;
        lastUnreadRef.current = notes.filter((n) => !n.is_read).length;
        return;
      }

      const fresh = notes
        .filter((n) => !seenIdsRef.current.has(n.id) && !n.is_read)
        .sort((a, b) => {
          const at = a.sent_at ? new Date(a.sent_at).getTime() : 0;
          const bt = b.sent_at ? new Date(b.sent_at).getTime() : 0;
          return at - bt;
        });

      for (const note of fresh) {
        seenIdsRef.current.add(note.id);
        const meta = getNotificationToastMeta(note.type, note.message);
        if (isNotificationToastSuppressed(note.type, meta.title)) {
          continue;
        }
        markNotificationToastShown(note.type, meta.title);
        showToast({
          title: meta.title,
          message: note.message,
          icon: meta.icon,
          variant: meta.variant,
          chipLabel: meta.chip,
          durationMs: 7000,
        });
      }

      if (fresh.length > 0) {
        window.dispatchEvent(new CustomEvent("mediai:notifications-changed"));
      }

      notes.forEach((n) => seenIdsRef.current.add(n.id));
      lastUnreadRef.current = notes.filter((n) => !n.is_read).length;
    },
    [showToast],
  );

  const poll = useCallback(async () => {
    try {
      const notes = await api<NotificationItem[]>(`${apiPrefix}/notifications`);
      processNotifications(notes);
    } catch {
      /* ignore polling errors */
    }
  }, [apiPrefix, processNotifications]);

  const pollUnreadCount = useCallback(async () => {
    try {
      const { count } = await api<{ count: number }>(`${apiPrefix}/notifications/unread-count`);
      if (initializedRef.current && count > lastUnreadRef.current) {
        await poll();
        return;
      }
      if (!initializedRef.current) {
        lastUnreadRef.current = count;
      }
    } catch {
      /* ignore */
    }
  }, [apiPrefix, poll]);

  useEffect(() => {
    void poll();
    const pollTimer = window.setInterval(() => void poll(), POLL_MS);
    const unreadTimer = window.setInterval(() => void pollUnreadCount(), UNREAD_CHECK_MS);
    const onFocus = () => void poll();
    const onVisibility = () => {
      if (document.visibilityState === "visible") void poll();
    };
    const onPollNow = () => void poll();

    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener(NOTIFICATIONS_POLL_EVENT, onPollNow);

    return () => {
      window.clearInterval(pollTimer);
      window.clearInterval(unreadTimer);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener(NOTIFICATIONS_POLL_EVENT, onPollNow);
    };
  }, [poll, pollUnreadCount]);
}
