export interface NotificationItem {
  id: string;
  type: string;
  message: string;
  sent_at: string | null;
  read_at?: string | null;
  is_read?: boolean;
}

export type NotificationToastVariant = "info" | "success" | "error" | "urgent";

export interface NotificationToastMeta {
  title: string;
  icon: string;
  variant: NotificationToastVariant;
  chip: string;
}

export function typeLabel(type: string): string {
  return getNotificationToastMeta(type).title;
}

export function typeIcon(type: string): string {
  return getNotificationToastMeta(type).icon;
}

export function toastVariantForNotificationType(type: string, message = ""): NotificationToastVariant {
  return getNotificationToastMeta(type, message).variant;
}

export function getNotificationToastMeta(type: string, message = ""): NotificationToastMeta {
  const lower = message.toLowerCase();

  if (type === "consultation_completed" || (type === "system" && lower.includes("consultation") && lower.includes("completed"))) {
    return { title: "Consultation complete", icon: "task_alt", variant: "success", chip: "Completed" };
  }
  if (type === "appointment_rescheduled" || (type === "booking_confirmation" && lower.includes("rescheduled"))) {
    return { title: "Appointment rescheduled", icon: "event_repeat", variant: "info", chip: "Rescheduled" };
  }
  if (type === "cancellation" || (type === "booking_confirmation" && lower.includes("cancelled"))) {
    return { title: "Appointment cancelled", icon: "event_busy", variant: "error", chip: "Cancelled" };
  }
  if (type === "booking_confirmation") {
    return { title: "Appointment booked", icon: "event_available", variant: "success", chip: "Booked" };
  }
  if (type === "reminder_scheduled") {
    return { title: "Reminder set", icon: "notifications_active", variant: "info", chip: "Reminder" };
  }
  if (type === "reminder") {
    return { title: "Appointment reminder", icon: "alarm", variant: "urgent", chip: "Due soon" };
  }
  if (type === "refill_approved") {
    return { title: "Refill approved", icon: "check_circle", variant: "success", chip: "Approved" };
  }
  if (type === "refill_denied") {
    return { title: "Refill denied", icon: "cancel", variant: "error", chip: "Denied" };
  }
  if (type === "refill_request") {
    return { title: "Refill request", icon: "medication", variant: "info", chip: "Refill" };
  }
  if (type === "video_consultation") {
    return { title: "Video consultation", icon: "videocam", variant: "info", chip: "Video" };
  }
  if (type === "urgent_consult_assigned") {
    return { title: "Urgent consult approved", icon: "check_circle", variant: "success", chip: "Urgent" };
  }
  if (type === "urgent_consult_declined") {
    return { title: "Urgent consult update", icon: "person_cancel", variant: "error", chip: "Urgent" };
  }
  if (type === "urgent_consult_expanded") {
    return { title: "More doctors notified", icon: "group_add", variant: "info", chip: "Urgent" };
  }
  if (type === "urgent_consult_unavailable") {
    return { title: "No doctors available", icon: "error", variant: "error", chip: "Urgent" };
  }
  if (type === "urgent_consult_request") {
    return { title: "Urgent consult request", icon: "emergency", variant: "urgent", chip: "Urgent" };
  }
  if (type === "urgent_consult_superseded") {
    return { title: "Urgent consult update", icon: "emergency", variant: "info", chip: "Urgent" };
  }
  if (type === "system") {
    return { title: "System update", icon: "info", variant: "info", chip: "Update" };
  }

  return { title: "Notification", icon: "notifications", variant: "info", chip: "Update" };
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
