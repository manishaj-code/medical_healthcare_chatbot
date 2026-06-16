export type ConsultationMode = "in_person" | "video" | "virtual" | (string & {});

export function normalizeConsultationMode(
  mode?: string | null,
  isVideo?: boolean,
): ConsultationMode {
  if (isVideo || mode === "video") return "video";
  if (mode === "virtual" || mode === "telehealth") return "virtual";
  if (!mode || mode === "in_person") return "in_person";
  return mode;
}

export function isVideoConsultation(visit: {
  is_video?: boolean;
  consultation_mode?: string;
}): boolean {
  return normalizeConsultationMode(visit.consultation_mode, visit.is_video) === "video";
}

export function consultationModeLabel(mode?: string | null, isVideo?: boolean): string {
  switch (normalizeConsultationMode(mode, isVideo)) {
    case "video":
      return "Video";
    case "virtual":
      return "Virtual";
    case "in_person":
      return "In-person";
    default:
      return (mode ?? "consultation").replace(/_/g, " ");
  }
}

export function consultationModeIcon(mode?: string | null, isVideo?: boolean): string {
  switch (normalizeConsultationMode(mode, isVideo)) {
    case "video":
      return "videocam";
    case "virtual":
      return "video_call";
    case "in_person":
      return "person";
    default:
      return "medical_services";
  }
}

/** Active visit eligible for the clinical consultation workflow (any delivery mode). */
export function canConductConsultation(status: string): boolean {
  const s = status.toLowerCase();
  return s !== "completed" && s !== "cancelled" && s !== "canceled";
}

/** Start consultation is only allowed for today's non-terminal appointments. */
export function canStartConsultation(
  appointmentDate: string,
  status: string,
  today = new Date().toISOString().slice(0, 10),
): boolean {
  return appointmentDate === today && canConductConsultation(status);
}
