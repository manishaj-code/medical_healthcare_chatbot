export interface DoctorAppointment {
  appointment_id: string;
  patient_id: string;
  patient_name: string;
  date: string;
  time: string;
  status: string;
}

export interface DoctorPatient {
  patient_id: string;
  name: string;
}

export function formatDoctorTime(t: string): string {
  const parts = t.split(":");
  if (parts.length < 2) return t;
  const h = parseInt(parts[0], 10);
  const m = parts[1];
  const ampm = h >= 12 ? "PM" : "AM";
  const hour = h % 12 || 12;
  return `${hour}:${m.slice(0, 2)} ${ampm}`;
}

export function patientInitials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

export function patientCaseId(patientId: string): string {
  return `#${patientId.replace(/-/g, "").slice(0, 4).toUpperCase()}`;
}

export function ageFromDob(dob: string | null | undefined): number | null {
  if (!dob) return null;
  const born = new Date(`${dob}T00:00:00`);
  if (Number.isNaN(born.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - born.getFullYear();
  const m = now.getMonth() - born.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < born.getDate())) age -= 1;
  return age;
}

export function formatDisplayDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function shiftIsoDate(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export function scheduleHeadingForDate(iso: string, today = todayIso()): string {
  if (iso === today) return "Today's schedule";
  if (iso === shiftIsoDate(today, 1)) return "Tomorrow's schedule";
  const d = new Date(`${iso}T12:00:00`);
  if (Number.isNaN(d.getTime())) return "Schedule";
  return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
}

export function isActiveAppointmentStatus(status: string): boolean {
  const s = status.toLowerCase();
  return s !== "cancelled" && s !== "canceled";
}

/** Future slot with a non-terminal status (confirmed, pending, etc.). */
export function isUpcomingAppointment(date: string, time: string, status: string): boolean {
  return isActiveAppointmentStatus(status) && !isAppointmentPast(date, time);
}

/** Slot time has passed but visit was never completed or cancelled. */
export function isOverdueAppointment(date: string, time: string, status: string): boolean {
  return isActiveAppointmentStatus(status) && isAppointmentPast(date, time);
}

export function queueVisitMetaForDate(iso: string, time: string, patientId: string, today = todayIso()): string {
  const when = formatDoctorTime(time);
  const caseId = patientCaseId(patientId);
  if (iso === today) return `Today's visit · ${when} · ${caseId}`;
  if (iso === shiftIsoDate(today, 1)) return `Tomorrow's visit · ${when} · ${caseId}`;
  return `Visit · ${formatDisplayDate(iso)} ${when} · ${caseId}`;
}

export function queueTagForScheduleDate(iso: string, today = todayIso()): string {
  if (iso === today) return "Today";
  if (iso === shiftIsoDate(today, 1)) return "Tomorrow";
  return formatDisplayDate(iso);
}

export function priorityQueueDescForDate(iso: string, today = todayIso()): string {
  if (iso === today) return "Patients needing your attention — refills and today's visits.";
  if (iso === shiftIsoDate(today, 1)) return "Patients needing your attention — refills and tomorrow's visits.";
  return `Patients needing your attention — refills and visits on ${formatDisplayDate(iso)}.`;
}

export function isAppointmentPast(date: string, time: string): boolean {
  const normalized = time.length === 5 ? `${time}:00` : time;
  const slot = new Date(`${date}T${normalized}`);
  return !Number.isNaN(slot.getTime()) && slot.getTime() < Date.now();
}

/** Drop today's (and any past) time slots that can no longer be booked. */
export function filterBookableSlots(slots: DoctorSlot[]): DoctorSlot[] {
  return slots.filter((s) => !isAppointmentPast(s.date, s.time));
}

export function summarizeText(text: string, maxLen = 220): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= maxLen) return clean;
  return `${clean.slice(0, maxLen).trim()}…`;
}

export interface DoctorSlot {
  date: string;
  time: string;
}

export interface SlotsByDay {
  date: string;
  times: string[];
  weekday: string;
  displayDate: string;
  isToday: boolean;
}

export function groupSlotsByDate(slots: DoctorSlot[]): SlotsByDay[] {
  const bookable = filterBookableSlots(slots);
  const map = new Map<string, string[]>();
  for (const s of bookable) {
    const list = map.get(s.date) ?? [];
    list.push(s.time);
    map.set(s.date, list);
  }

  const today = todayIso();
  return [...map.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, times]) => {
      const d = new Date(`${date}T12:00:00`);
      const weekday = Number.isNaN(d.getTime())
        ? ""
        : d.toLocaleDateString("en-US", { weekday: "long" });
      return {
        date,
        times: [...times].sort(),
        weekday,
        displayDate: formatDisplayDate(date),
        isToday: date === today,
      };
    })
    .filter((day) => day.times.length > 0);
}
