export interface VideoConsultationSession {
  appointment_id: string;
  apt_id: string;
  room_id: string;
  token: string;
  url: string;
  doctor_name?: string;
  patient_name?: string;
  slot_date?: string;
  slot_time?: string;
  consultation_mode?: string;
}

export type VideoParticipantRole = "patient" | "doctor";
