import type { ChatUiPayload } from "../components/ChatBookingUI";

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
      slots: (d.slots ?? []).slice(0, 6).map((s) => ({
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

export async function resolveBookingUi(
  ui: ChatUiPayload | null | undefined,
  agent?: string,
  content?: string
): Promise<ChatUiPayload | null> {
  if (ui?.type === "doctor_list" && ui.doctors?.length) return ui;
  if (ui?.type === "slot_list" && ui.slots?.length) return ui;
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
