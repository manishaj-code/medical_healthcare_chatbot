import type { ChatUiPayload } from "../components/ChatBookingUI";

export function isChatSlotPast(slotDate?: string, slotTime?: string): boolean {
  if (!slotDate || !slotTime) return false;
  const normalized = slotTime.length === 5 ? `${slotTime}:00` : slotTime;
  const slot = new Date(`${slotDate}T${normalized}`);
  return !Number.isNaN(slot.getTime()) && slot.getTime() < Date.now();
}

export function filterChatBookableSlots<
  T extends { slot_date?: string; slot_time?: string },
>(slots: T[]): T[] {
  return slots.filter((s) => !isChatSlotPast(s.slot_date, s.slot_time));
}

interface ReminderSyncMessage {
  role: string;
  content: string;
  ui?: ChatUiPayload | null;
}

function appointmentCardKey(ui: ChatUiPayload): string | null {
  if (ui.type !== "appointment_confirmed") return null;
  if (ui.appointment_id) return `id:${ui.appointment_id}`;
  if (ui.apt_id) return `apt:${ui.apt_id}`;
  return null;
}

/** Disable actions on older copies when a newer card exists for the same appointment. */
export function markSupersededAppointmentCards<T extends ReminderSyncMessage>(messages: T[]): T[] {
  const latestIndexByKey = new Map<string, number>();
  messages.forEach((msg, index) => {
    const key = msg.ui ? appointmentCardKey(msg.ui) : null;
    if (key) latestIndexByKey.set(key, index);
  });
  if (!latestIndexByKey.size) return messages;

  return messages.map((msg, index) => {
    const ui = msg.ui;
    if (!ui || ui.type !== "appointment_confirmed") return msg;
    const key = appointmentCardKey(ui);
    if (!key || latestIndexByKey.get(key) === index) return msg;
    if (ui.actions_disabled) return msg;
    return { ...msg, ui: { ...ui, actions_disabled: true } };
  });
}

export function finalizeChatMessages<T extends ReminderSyncMessage>(messages: T[]): T[] {
  return markSupersededAppointmentCards(syncAppointmentReminderState(messages));
}

/** Keep all appointment cards in sync when any copy shows reminder_set. */
export function syncAppointmentReminderState<T extends ReminderSyncMessage>(messages: T[]): T[] {
  const reminded = new Set<string>();
  for (const msg of messages) {
    const ui = msg.ui;
    if (ui?.type !== "appointment_confirmed") continue;
    if (ui.reminder_set) {
      if (ui.apt_id) reminded.add(`apt:${ui.apt_id}`);
      if (ui.appointment_id) reminded.add(`id:${ui.appointment_id}`);
    }
    if (
      msg.role === "assistant" &&
      /reminder set|already have a reminder/i.test(msg.content) &&
      ui?.appointment_id
    ) {
      if (ui.apt_id) reminded.add(`apt:${ui.apt_id}`);
      reminded.add(`id:${ui.appointment_id}`);
    }
  }
  if (!reminded.size) return messages;
  return messages.map((msg) => {
    const ui = msg.ui;
    if (ui?.type !== "appointment_confirmed" || ui.reminder_set) return msg;
    const matches =
      (ui.apt_id && reminded.has(`apt:${ui.apt_id}`)) ||
      (ui.appointment_id && reminded.has(`id:${ui.appointment_id}`));
    if (!matches) return msg;
    return { ...msg, ui: { ...ui, reminder_set: true } };
  });
}

interface ApiDoctor {
  id: string;
  name: string;
  specialty: string;
  experience_years: number;
  rating: number;
  slots: {
    doctor_id: string;
    doctor_name: string;
    slot_date: string;
    slot_time: string;
    label: string;
  }[];
}

export function buildDoctorListUi(doctors: ApiDoctor[]): ChatUiPayload {
  return {
    type: "doctor_list",
    total: doctors.length,
    doctors: doctors.map((d) => ({
      id: d.id,
      name: d.name,
      specialty: d.specialty,
      experience_years: d.experience_years,
      rating: d.rating,
      slots: filterChatBookableSlots(d.slots ?? [])
        .slice(0, 6)
        .map((s) => ({
          label: s.label,
          doctor_id: s.doctor_id ?? d.id,
          doctor_name: s.doctor_name ?? d.name,
          slot_date: s.slot_date,
          slot_time: s.slot_time,
          message: `${d.name} ${s.label}`,
        })),
    })),
  };
}

function isDoctorListIntro(content: string): boolean {
  return /i found \*\*\d+ doctors?\*\*/i.test(content) || /here are \*\*\d+ doctors?\*\*/i.test(content);
}

function isBookingOfferPrompt(content?: string): boolean {
  return !!content && /would you like me to show available doctors/i.test(content);
}

function parseConfirmBookingUi(content: string): ChatUiPayload | null {
  if (!/before booking, please confirm/i.test(content)) return null;
  const patient = content.match(/Patient Name:\s*(.+)/i)?.[1]?.trim();
  const doctor = content.match(/Doctor:\s*(.+)/i)?.[1]?.trim();
  const slot = content.match(/Date & Time:\s*(.+)/i)?.[1]?.trim();
  return {
    type: "confirm_booking",
    patient_name: patient,
    doctor_name: doctor,
    label: slot,
    options: [
      { label: "Yes, confirm booking", message: "Yes" },
      { label: "No, cancel", message: "No" },
    ],
  };
}

function parseBookingOfferUi(content: string): ChatUiPayload | null {
  if (!isBookingOfferPrompt(content)) return null;
  return {
    type: "yes_no",
    options: [
      { label: "Yes, show doctors", message: "Yes" },
      { label: "No thanks", message: "No" },
    ],
  };
}

/** Booking confirmation cards stay visible in chat history (not only on the latest turn). */
export function isPersistentBookingCard(ui?: ChatUiPayload | null): boolean {
  return ui?.type === "appointment_confirmed" && !!ui.appointment_id;
}

/** Hide redundant prose when the structured booking card carries the details. */
export function shouldHideBookingCardCaption(ui?: ChatUiPayload | null): boolean {
  return (
    ui?.type === "confirm_booking" ||
    ui?.type === "confirm_reschedule" ||
    ui?.type === "reschedule_slots" ||
    ui?.type === "appointment_confirmed"
  );
}

export function shouldShowInteractiveBookingUi(
  ui: ChatUiPayload | undefined | null,
  messageIndex: number,
  lastAssistantIdx: number
): boolean {
  if (!ui) return false;
  return messageIndex === lastAssistantIdx || isPersistentBookingCard(ui);
}

export async function resolveBookingUi(
  ui: ChatUiPayload | null | undefined,
  agent?: string,
  content?: string
): Promise<ChatUiPayload | null> {
  if (ui?.type === "doctor_list" && ui.doctors?.length) return ui;
  if (ui?.type === "slot_list" && ui.slots?.length) return ui;
  if (ui?.type === "reschedule_slots" && ui.slots?.length) return ui;
  if (ui?.type === "appointment_confirmed" && ui.appointment_id) return ui;
  if (ui?.type === "confirm_booking" && ui.options?.length) return ui;
  if (ui?.type === "confirm_reschedule" && ui.options?.length) return ui;
  if (ui?.type === "yes_no" && ui.options?.length) return ui;
  if (ui?.type === "symptom_picker" && ui.options?.length) return ui;
  if (ui?.type === "duration_picker" && ui.options?.length) return ui;
  if (ui?.type === "severity_picker" && ui.options?.length) return ui;

  if (content) {
    const confirmUi = parseConfirmBookingUi(content);
    if (confirmUi) return confirmUi;
    const offerUi = parseBookingOfferUi(content);
    if (offerUi) return offerUi;
  }

  // Never attach doctor list UI to the triage offer prompt — wait for yes/doctor pick
  if (isBookingOfferPrompt(content)) return ui ?? null;

  // Only attach doctor UI to real doctor-list responses — not Yes/No offer prompts
  const shouldFetch =
    agent === "doctor_discovery" ||
    (agent === "appointment" && content && isDoctorListIntro(content)) ||
    (!ui && agent && agent !== "symptom_assessment" && content && isDoctorListIntro(content));

  if (!shouldFetch) return ui ?? null;

  const { api } = await import("../api/client");
  try {
    const doctors = await api<ApiDoctor[]>("/api/v1/doctors/with-availability");
    if (!doctors.length) return ui ?? null;
    return buildDoctorListUi(doctors);
  } catch {
    return ui ?? null;
  }
}
