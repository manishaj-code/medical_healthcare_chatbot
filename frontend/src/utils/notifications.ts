export interface NotificationItem {
  id: string;
  type: string;
  message: string;
  sent_at: string | null;
  read_at?: string | null;
  is_read?: boolean;
}

export function typeLabel(type: string): string {
  if (type === "refill_approved") return "Refill approved";
  if (type === "refill_denied") return "Refill denied";
  if (type === "refill_request") return "Refill request";
  if (type === "booking_confirmation") return "Appointment";
  if (type === "reminder" || type === "reminder_scheduled") return "Reminder";
  if (type === "video_consultation") return "Video consult";
  if (type === "cancellation") return "Cancelled";
  if (type === "system") return "System";
  return "Update";
}

export function typeIcon(type: string): string {
  if (type === "refill_approved") return "check_circle";
  if (type === "refill_denied") return "cancel";
  if (type === "refill_request") return "medication";
  if (type === "booking_confirmation") return "event";
  if (type === "reminder" || type === "reminder_scheduled") return "alarm";
  if (type === "video_consultation") return "videocam";
  if (type === "cancellation") return "event_busy";
  if (type === "system") return "info";
  return "notifications";
}

export function formatNotificationTime(sentAt: string | null): string {
  if (!sentAt) return "";
  const date = new Date(sentAt);
  const diffMs = Date.now() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}
