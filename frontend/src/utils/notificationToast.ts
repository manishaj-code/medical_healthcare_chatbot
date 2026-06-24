import type { ToastItem } from "../components/toast/ToastProvider";
import type { NotificationItem } from "./notifications";
import { getNotificationToastMeta } from "./notifications";
import { markNotificationToastShown } from "./toastSuppression";

export const NOTIFICATIONS_POLL_EVENT = "mediai:poll-notifications";

type ShowToast = (toast: Omit<ToastItem, "id">) => void;

/** Refresh bell badge only — does not flash another toast from the poller. */
export function requestNotificationBadgeRefresh() {
  window.dispatchEvent(new CustomEvent("mediai:notifications-changed"));
}

export function requestNotificationPoll() {
  window.dispatchEvent(new CustomEvent(NOTIFICATIONS_POLL_EVENT));
  requestNotificationBadgeRefresh();
}

export function showNotificationToast(showToast: ShowToast, note: Pick<NotificationItem, "type" | "message">) {
  const meta = getNotificationToastMeta(note.type, note.message);
  markNotificationToastShown(note.type, meta.title);
  showToast({
    title: meta.title,
    message: note.message,
    icon: meta.icon,
    variant: meta.variant,
    chipLabel: meta.chip,
    durationMs: 7000,
  });
  requestNotificationBadgeRefresh();
}

export function notifyAppointmentBooked(
  showToast: ShowToast,
  opts: { doctorName?: string; label?: string; message?: string },
) {
  const message =
    opts.message ??
    (opts.doctorName && opts.label
      ? `Your appointment was confirmed with ${opts.doctorName} on ${opts.label}.`
      : "Your appointment has been confirmed.");

  showNotificationToast(showToast, { type: "booking_confirmation", message });
}

export function notifyFromChatUi(
  showToast: ShowToast,
  ui: {
    type?: string;
    status?: string;
    doctor_name?: string;
    label?: string;
    apt_id?: string;
    patient_name?: string;
    reminder_set?: boolean;
  } | null | undefined,
  userMessage?: string,
) {
  if (!ui?.type) {
    if (userMessage && /^\[set_reminder:/i.test(userMessage.trim())) {
      showNotificationToast(showToast, {
        type: "reminder_scheduled",
        message: "We'll remind you 30 minutes before your appointment.",
      });
    }
    return;
  }

  if (ui.type === "appointment_confirmed") {
    if (userMessage && /^\[set_reminder:/i.test(userMessage.trim())) {
      const reminderMessage =
        ui.doctor_name && ui.label
          ? `We'll remind you 30 minutes before your appointment with ${ui.doctor_name} on ${ui.label}.`
          : ui.apt_id
            ? `We'll remind you 30 minutes before appointment ${ui.apt_id}.`
            : "We'll remind you 30 minutes before your appointment.";
      showNotificationToast(showToast, {
        type: "reminder_scheduled",
        message: reminderMessage,
      });
      return;
    }

    const status = ui.status ?? "confirmed";
    if (status === "cancelled") {
      showNotificationToast(showToast, {
        type: "cancellation",
        message: ui.label
          ? `Your appointment${ui.apt_id ? ` ${ui.apt_id}` : ""} on ${ui.label} was cancelled.`
          : `Your appointment${ui.apt_id ? ` ${ui.apt_id}` : ""} was cancelled.`,
      });
    } else if (status === "rescheduled") {
      const message =
        ui.doctor_name && ui.label
          ? `Your appointment was rescheduled with ${ui.doctor_name} on ${ui.label}.`
          : ui.label
            ? `Your appointment was rescheduled to ${ui.label}.`
            : "Your appointment was rescheduled.";
      showNotificationToast(showToast, {
        type: "appointment_rescheduled",
        message,
      });
    } else if (status === "completed") {
      showNotificationToast(showToast, {
        type: "consultation_completed",
        message: "Your consultation is complete. View health records for details.",
      });
    } else {
      notifyAppointmentBooked(showToast, {
        doctorName: ui.doctor_name,
        label: ui.label,
      });
      return;
    }
    return;
  }

  if (ui.type === "video_consultation") {
    showNotificationToast(showToast, {
      type: "video_consultation",
      message: ui.doctor_name
        ? `Video room ready with ${ui.doctor_name}.`
        : "Your video consultation room is ready.",
    });
    return;
  }

  if (ui.type === "urgent_consult_accepted") {
    showNotificationToast(showToast, {
      type: "urgent_consult_assigned",
      message: ui.doctor_name
        ? `Urgent consult assigned to ${ui.doctor_name}.`
        : "Your urgent consultation has been assigned.",
    });
    return;
  }

  if (ui.type === "urgent_consult_pending") {
    showNotificationToast(showToast, {
      type: "urgent_consult_request",
      message: "We're notifying available doctors for your urgent consult.",
    });
    return;
  }

  if (userMessage && /^\[set_reminder:/i.test(userMessage.trim())) {
    showNotificationToast(showToast, {
      type: "reminder_scheduled",
      message: "We'll remind you 30 minutes before your appointment.",
    });
  }
}
