import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { NotificationItem } from "../utils/notifications";

const POLL_MS = 60000;

export function useNotifications(apiPrefix: string) {
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const res = await api<{ count: number }>(`${apiPrefix}/notifications/unread-count`);
      setUnreadCount(res.count);
    } catch {
      setUnreadCount(0);
    }
  }, [apiPrefix]);

  const fetchPreview = useCallback(
    async (limit = 5) => {
      setLoading(true);
      try {
        const notes = await api<NotificationItem[]>(`${apiPrefix}/notifications`);
        setNotifications(notes.slice(0, limit));
      } catch {
        setNotifications([]);
      }
      setLoading(false);
    },
    [apiPrefix]
  );

  const markRead = useCallback(
    async (ids?: string[]) => {
      try {
        await api<{ marked: number }>(`${apiPrefix}/notifications/mark-read`, {
          method: "POST",
          body: JSON.stringify({ ids: ids ?? null }),
        });
        setUnreadCount(0);
        setNotifications((prev) =>
          prev.map((n) => ({ ...n, is_read: true, read_at: n.read_at ?? new Date().toISOString() }))
        );
      } catch {
        /* keep badge if mark-read fails */
      }
    },
    [apiPrefix]
  );

  useEffect(() => {
    void fetchUnreadCount();
    const timer = window.setInterval(() => void fetchUnreadCount(), POLL_MS);
    const onFocus = () => void fetchUnreadCount();
    const onChanged = () => void fetchUnreadCount();
    window.addEventListener("focus", onFocus);
    window.addEventListener("mediai:notifications-changed", onChanged);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("mediai:notifications-changed", onChanged);
    };
  }, [fetchUnreadCount]);

  return {
    unreadCount,
    notifications,
    loading,
    fetchUnreadCount,
    fetchPreview,
    markRead,
  };
}
