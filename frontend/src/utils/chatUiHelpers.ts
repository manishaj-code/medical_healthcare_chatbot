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
  return (
    !!content &&
    (/would you like me to show available doctors/i.test(content) ||
      /would you like to book an appointment/i.test(content))
  );
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
  const showDoctors = /show available doctors/i.test(content);
  return {
    type: showDoctors ? "yes_no" : "post_assessment",
    options: showDoctors
      ? [
          { label: "Yes, show doctors", message: "Yes" },
          { label: "No thanks", message: "No" },
        ]
      : [
          { label: "Self-care tips", message: "Tell me self-care advice for my symptoms" },
          { label: "Book appointment", message: "Book appointment" },
        ],
  };
}

function parseDurationPickerUi(content: string): ChatUiPayload | null {
  if (!/how long have you been experiencing/i.test(content)) return null;
  return {
    type: "duration_picker",
    variant: "stack",
    options: [
      { label: "Less than 1 day", message: "Less than 1 day" },
      { label: "1–3 days", message: "1-3 days" },
      { label: "4–7 days", message: "4-7 days" },
      { label: "Over 1 week", message: "Over 1 week" },
      { label: "Not sure", message: "Not sure" },
    ],
  };
}

function parseSeverityPickerUi(content: string): ChatUiPayload | null {
  if (!/severity of your symptoms|describe the severity/i.test(content)) return null;
  return {
    type: "severity_picker",
    variant: "stack",
    options: [
      { label: "Mild", message: "Mild" },
      { label: "Moderate", message: "Moderate" },
      { label: "Severe", message: "Severe" },
      { label: "Not sure", message: "Not sure" },
    ],
  };
}

function parseMoreSymptomsUi(content: string): ChatUiPayload | null {
  const lower = content.toLowerCase();
  if (/type them below|type freely below|please type the other symptoms/i.test(lower)) {
    return null;
  }
  if (
    /^are you experiencing any other symptoms/i.test(content.trim()) ||
    /any other symptoms, or should i summarize/i.test(lower)
  ) {
    return {
      type: "more_symptoms",
      variant: "stack",
      options: [
        { label: "Yes, more symptoms", message: "Yes, I have more symptoms" },
        { label: "No, that's all", message: "No other symptoms" },
      ],
    };
  }
  return null;
}

function parseYesNoUi(content: string): ChatUiPayload | null {
  if (/do you have any breathing/i.test(content)) {
    return {
      type: "yes_no",
      options: [
        { label: "Yes", message: "Yes" },
        { label: "No", message: "No" },
      ],
    };
  }
  if (/existing conditions|diabetes, asthma/i.test(content)) {
    return {
      type: "yes_no",
      options: [
        { label: "Yes", message: "Yes" },
        { label: "No conditions", message: "No" },
      ],
    };
  }
  return null;
}

/** Infer structured quick-action UI from assistant text when the API omitted `ui`. */
export function resolveChatUiSync(
  ui: ChatUiPayload | null | undefined,
  content?: string
): ChatUiPayload | null {
  if (ui?.options?.length) return ui;
  if (ui?.type === "doctor_list" && ui.doctors?.length) return ui;
  if (ui?.type === "slot_list" && ui.slots?.length) return ui;
  if (ui?.type === "appointment_confirmed" && ui.appointment_id) return ui;
  if (!content) return ui ?? null;
  return (
    parseConfirmBookingUi(content) ??
    parseBookingOfferUi(content) ??
    parseDurationPickerUi(content) ??
    parseSeverityPickerUi(content) ??
    parseMoreSymptomsUi(content) ??
    parseYesNoUi(content) ??
    ui ??
    null
  );
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
    ui?.type === "appointment_confirmed" ||
    ui?.type === "urgent_consult_pending" ||
    ui?.type === "urgent_consult_accepted"
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
  const resolved = resolveChatUiSync(ui, content);
  if (resolved?.options?.length) return resolved;
  if (resolved?.type === "appointment_confirmed" && resolved.appointment_id) return resolved;
  if (resolved?.type === "slot_list" && resolved.slots?.length) return resolved;
  if (resolved?.type === "reschedule_slots" && resolved.slots?.length) return resolved;
  if (resolved?.type === "doctor_list" && resolved.doctors?.length) return resolved;

  // Never attach doctor list UI to the triage offer prompt — wait for yes/doctor pick
  if (isBookingOfferPrompt(content)) return resolved ?? null;

  // Only attach doctor UI to real doctor-list responses — not Yes/No offer prompts
  const shouldFetch =
    agent === "doctor_discovery" ||
    (agent === "appointment" && content && isDoctorListIntro(content)) ||
    (!ui && agent && agent !== "symptom_assessment" && content && isDoctorListIntro(content));

  if (!shouldFetch) return resolved ?? null;

  const { api } = await import("../api/client");
  try {
    const doctors = await api<ApiDoctor[]>("/api/v1/doctors/with-availability");
    if (!doctors.length) return resolved ?? null;
    return buildDoctorListUi(doctors);
  } catch {
    return resolved ?? null;
  }
}
