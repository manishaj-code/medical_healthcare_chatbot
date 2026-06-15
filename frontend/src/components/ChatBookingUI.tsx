import { useState, useMemo, useEffect } from "react";
import type { ReactNode } from "react";
import DoctorAvatar from "./DoctorAvatar";
import { api } from "../api/client";
import { buildSetReminderMessage } from "../utils/chatTokens";
import { filterChatBookableSlots } from "../utils/chatUiHelpers";
import {
  buildCancelAppointmentMessage,
  buildRescheduleAppointmentMessage,
} from "../utils/appointmentChatActions";

interface SlotUi {
  label: string;
  doctor_id: string;
  doctor_name: string;
  message: string;
  slot_date?: string;
  slot_time?: string;
}

interface DoctorUi {
  id: string;
  name: string;
  specialty: string;
  experience_years: number;
  rating: number | null;
  profile_image_url?: string | null;
  consultation_fee?: number | null;
  hospital_name?: string | null;
  professional_summary?: string | null;
  next_available?: string | null;
  slots: SlotUi[];
}

export interface ChoiceOption {
  label: string;
  message: string;
}

const CHOICE_MENU_TYPES = new Set([
  "yes_no",
  "symptom_picker",
  "symptom_starter",
  "duration_picker",
  "severity_picker",
  "more_symptoms",
  "action_menu",
  "welcome_actions",
  "post_assessment",
  "find_doctor_menu",
  "specialty_picker",
  "report_upload_menu",
  "report_followup",
  "nav_menu",
]);

export interface ChatUiPayload {
  type:
    | "doctor_list"
    | "slot_list"
    | "reschedule_slots"
    | "appointment_confirmed"
    | "confirm_booking"
    | "confirm_reschedule"
    | "yes_no"
    | "symptom_picker"
    | "symptom_starter"
    | "duration_picker"
    | "severity_picker"
    | "more_symptoms"
    | "action_menu"
    | "welcome_actions"
    | "post_assessment"
    | "find_doctor_menu"
    | "specialty_picker"
    | "report_upload_menu"
    | "report_followup"
    | "nav_menu"
    | "video_consultation"
    | "symptom_image_hint"
    | "urgent_consult_pending"
    | "urgent_consult_accepted";
  variant?: "pill" | "stack";
  join_url?: string;
  apt_id?: string;
  doctor_name?: string;
  total?: number;
  doctors?: DoctorUi[];
  doctor_id?: string;
  doctor_name?: string;
  slots?: SlotUi[];
  appointment_id?: string;
  apt_id?: string;
  label?: string;
  patient_name?: string;
  current?: string;
  current_time?: string;
  specialty?: string;
  hospital_name?: string;
  status?: "confirmed" | "rescheduled" | "cancelled";
  reminder_set?: boolean;
  actions_disabled?: boolean;
  request_id?: string;
  risk_level?: string;
  symptoms?: string[];
  expires_at?: string;
  join_url?: string;
  options?: ChoiceOption[];
}

interface Props {
  ui: ChatUiPayload;
  disabled?: boolean;
  onPick: (message: string) => void | Promise<void>;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

/** Extract the time portion from a slot label like "Today: 9:00 AM" → "9:00 AM" */
function slotTime(label: string): string {
  const match = label.match(/^[^:]+:\s*(.+)$/);
  return match ? match[1].trim() : label;
}

/** Group slots by their day prefix for the SlotButtons fallback */
function groupSlots(slots: SlotUi[]): { day: string; items: SlotUi[] }[] {
  const map = new Map<string, SlotUi[]>();
  for (const slot of slots) {
    const colonIdx = slot.label.indexOf(":");
    const day = colonIdx > 0 ? slot.label.slice(0, colonIdx).trim() : "Other";
    if (!map.has(day)) map.set(day, []);
    map.get(day)!.push(slot);
  }
  return Array.from(map.entries()).map(([day, items]) => ({ day, items }));
}

/**
 * Parse a slot label into a Date.
 * Formats: "Today: 9:00 AM" | "Tomorrow: 2:30 PM" | "2024-06-12: 9:00 AM"
 */
function parseSlotDate(label: string): Date | null {
  try {
    const colonIdx = label.indexOf(":");
    if (colonIdx < 0) return null;
    const datePart = label.slice(0, colonIdx).trim();
    const timeStr = label.slice(colonIdx + 1).trim();

    const todayMidnight = new Date();
    todayMidnight.setHours(0, 0, 0, 0);

    let baseDate: Date;
    const lower = datePart.toLowerCase();
    if (lower === "today") {
      baseDate = new Date(todayMidnight);
    } else if (lower === "tomorrow") {
      baseDate = new Date(todayMidnight);
      baseDate.setDate(todayMidnight.getDate() + 1);
    } else {
      baseDate = new Date(`${datePart}T00:00:00`);
      if (isNaN(baseDate.getTime())) return null;
    }

    const timeMatch = timeStr.match(/(\d{1,2}):(\d{2})\s*(AM|PM)/i);
    if (!timeMatch) return null;
    let hours = parseInt(timeMatch[1], 10);
    const minutes = parseInt(timeMatch[2], 10);
    const meridiem = timeMatch[3].toUpperCase();
    if (meridiem === "PM" && hours < 12) hours += 12;
    if (meridiem === "AM" && hours === 12) hours = 0;

    const result = new Date(baseDate);
    result.setHours(hours, minutes, 0, 0);
    return result;
  } catch {
    return null;
  }
}

function isSlotPast(label: string): boolean {
  const d = parseSlotDate(label);
  return d ? d < new Date() : false;
}

function slotMidnight(label: string): Date | null {
  const d = parseSlotDate(label);
  if (!d) return null;
  const m = new Date(d);
  m.setHours(0, 0, 0, 0);
  return m;
}

function getSlotsForDate(slots: SlotUi[], date: Date): SlotUi[] {
  return slots.filter((s) => {
    const m = slotMidnight(s.label);
    if (!m) return false;
    return (
      m.getFullYear() === date.getFullYear() &&
      m.getMonth() === date.getMonth() &&
      m.getDate() === date.getDate()
    );
  });
}

/** Build a full month calendar grid (up to 6 weeks × 7 days) */
function buildMonthCalendar(year: number, month: number): { weeks: (Date | null)[][] } {
  const firstDay = new Date(year, month, 1);
  const startDow = firstDay.getDay(); // 0=Sun
  const mondayOffset = startDow === 0 ? -6 : 1 - startDow;
  const gridStart = new Date(firstDay);
  gridStart.setDate(firstDay.getDate() + mondayOffset);

  const weeks: (Date | null)[][] = [];
  const cursor = new Date(gridStart);

  for (let w = 0; w < 6; w++) {
    const week: (Date | null)[] = [];
    for (let d = 0; d < 7; d++) {
      week.push(cursor.getMonth() === month ? new Date(cursor) : null);
      cursor.setDate(cursor.getDate() + 1);
    }
    weeks.push(week);
    if (cursor.getMonth() !== month && w >= 3) break;
  }
  return { weeks };
}

const WEEKDAY_LABELS = ["M", "T", "W", "T", "F", "S", "S"];
const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

// ─── AppointmentPicker ───────────────────────────────────────────────────────

function AppointmentPicker({
  doctor,
  slots,
  disabled,
  onPick,
}: {
  doctor: DoctorUi;
  slots: SlotUi[];
  disabled?: boolean;
  onPick: (message: string) => void;
}) {
  const firstSlotDate = useMemo(() => {
    // Find the earliest FUTURE slot date to open the calendar on
    const todayMs = new Date().setHours(0, 0, 0, 0);
    const dates = slots
      .map((s) => slotMidnight(s.label))
      .filter((d): d is Date => d !== null && d.getTime() >= todayMs)
      .sort((a, b) => a.getTime() - b.getTime());
    return dates[0] ?? new Date();
  }, [slots]);

  const [calYear, setCalYear] = useState(firstSlotDate.getFullYear());
  const [calMonth, setCalMonth] = useState(firstSlotDate.getMonth());

  const slotDayKeys = useMemo(() => {
    const set = new Set<string>();
    for (const s of slots) {
      const m = slotMidnight(s.label);
      if (m) set.add(`${m.getFullYear()}-${m.getMonth()}-${m.getDate()}`);
    }
    return set;
  }, [slots]);

  const defaultSelected = useMemo(() => {
    const todayMidnight = new Date();
    todayMidnight.setHours(0, 0, 0, 0);
    const days = slots
      .map((s) => slotMidnight(s.label))
      .filter((d): d is Date => d !== null && d >= todayMidnight)
      .sort((a, b) => a.getTime() - b.getTime());
    return days[0] ?? null;
  }, [slots]);

  const [selectedDate, setSelectedDate] = useState<Date | null>(defaultSelected);

  // Reset when doctor changes
  useEffect(() => {
    setSelectedDate(defaultSelected);
    if (defaultSelected) {
      setCalYear(defaultSelected.getFullYear());
      setCalMonth(defaultSelected.getMonth());
    }
  }, [doctor.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const { weeks } = useMemo(() => buildMonthCalendar(calYear, calMonth), [calYear, calMonth]);

  const visibleSlots = useMemo(
    () => (selectedDate ? getSlotsForDate(slots, selectedDate) : []),
    [slots, selectedDate]
  );

  const todayMidnight = new Date();
  todayMidnight.setHours(0, 0, 0, 0);

  const now = new Date();
  const isPrevDisabled = calYear === now.getFullYear() && calMonth === now.getMonth();

  function prevMonth() {
    if (calMonth === 0) { setCalMonth(11); setCalYear((y) => y - 1); }
    else setCalMonth((m) => m - 1);
  }
  function nextMonth() {
    if (calMonth === 11) { setCalMonth(0); setCalYear((y) => y + 1); }
    else setCalMonth((m) => m + 1);
  }

  const hasAvailableSlot = visibleSlots.some((s) => !isSlotPast(s.label));

  // Track which specific slot the user has selected
  const [selectedSlot, setSelectedSlot] = useState<SlotUi | null>(null);

  // Reset selected slot when date or doctor changes
  useEffect(() => {
    setSelectedSlot(null);
  }, [selectedDate, doctor.id]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="appt-picker">
      {/* Selected doctor header */}
      <div className="appt-doctor-header">
        <DoctorAvatar
          name={doctor.name}
          profileImageUrl={doctor.profile_image_url}
          className="appt-doctor-avatar appt-doctor-avatar--photo"
          initialsClassName="appt-doctor-avatar"
        />
        <div className="appt-doctor-header-info">
          <span className="appt-doctor-header-name">{doctor.name}</span>
          <span className="appt-doctor-header-meta">
            {doctor.specialty}
            {doctor.experience_years > 0 && ` · ${doctor.experience_years}+ yrs exp`}
          </span>
        </div>
        {doctor.rating != null && (
          <span className="appt-doctor-header-rating">★ {doctor.rating}</span>
        )}
      </div>

      <h3 className="appt-picker-title">Select Appointment</h3>

      <div className="appt-calendar-panel">
      {/* Month navigation */}
      <div className="appt-cal-header">
        <span className="appt-cal-month">{MONTH_NAMES[calMonth]} {calYear}</span>
        <div className="appt-cal-nav">
          <button
            type="button"
            className="appt-cal-nav-btn"
            onClick={prevMonth}
            disabled={isPrevDisabled || disabled}
            aria-label="Previous month"
          >‹</button>
          <button
            type="button"
            className="appt-cal-nav-btn"
            onClick={nextMonth}
            disabled={disabled}
            aria-label="Next month"
          >›</button>
        </div>
      </div>

      {/* Full month calendar */}
      <div className="appt-cal-grid">
        {WEEKDAY_LABELS.map((l, i) => (
          <span key={i} className="appt-cal-weekday">{l}</span>
        ))}
        {weeks.flat().map((date, i) => {
          if (!date) {
            return <span key={`empty-${i}`} className="appt-cal-day appt-cal-day--outside" />;
          }
          const key = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
          const hasSlots = slotDayKeys.has(key);
          const isPast = date < todayMidnight;
          const isSelected =
            selectedDate !== null &&
            date.getFullYear() === selectedDate.getFullYear() &&
            date.getMonth() === selectedDate.getMonth() &&
            date.getDate() === selectedDate.getDate();
          const isToday =
            date.getFullYear() === todayMidnight.getFullYear() &&
            date.getMonth() === todayMidnight.getMonth() &&
            date.getDate() === todayMidnight.getDate();

          const cls = [
            "appt-cal-day",
            isSelected ? "appt-cal-day--selected" : "",
            isToday && !isSelected ? "appt-cal-day--today" : "",
            isPast ? "appt-cal-day--past" : "",
            !isPast && hasSlots ? "appt-cal-day--has-slots" : "",
            !isPast && !hasSlots ? "appt-cal-day--no-slots" : "",
          ].filter(Boolean).join(" ");

          return (
            <button
              key={key}
              type="button"
              className={cls}
              disabled={isPast || disabled}
              onClick={() => setSelectedDate(date)}
              title={
                isPast ? "Past date"
                : hasSlots ? "Has available slots"
                : "No slots on this day"
              }
            >
              {date.getDate()}
            </button>
          );
        })}
      </div>

      {/* No slots in this month hint */}
      {!weeks.flat().some((d) => {
        if (!d) return false;
        const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
        return slotDayKeys.has(key) && d >= todayMidnight;
      }) && (
        <p className="appt-cal-no-slots-hint">
          No slots in {MONTH_NAMES[calMonth]} — try next month ›
        </p>
      )}
      </div>

      {/* Time slots */}
      <div className="appt-slots-section">
        <span className="appt-slots-label">
          Available Slots
          {selectedDate && (
            <span className="appt-slots-date-label">
              {" — "}{selectedDate.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}
            </span>
          )}
        </span>
        <div className="appt-slots-grid">
          {!selectedDate && (
            <p className="appt-slots-empty">Select a date to view slots.</p>
          )}
          {selectedDate && visibleSlots.length === 0 && (
            <p className="appt-slots-empty">No slots available on this date.</p>
          )}
          {visibleSlots.map((slot, i) => {
            const past = isSlotPast(slot.label);
            const time = slotTime(slot.label);
            const isChipSelected = selectedSlot?.label === slot.label;
            return (
              <button
                key={`${slot.label}-${i}`}
                type="button"
                className={[
                  "appt-slot-chip",
                  past ? "appt-slot-chip--past" : "",
                  isChipSelected ? "appt-slot-chip--selected" : "",
                ].filter(Boolean).join(" ")}
                disabled={disabled || past}
                onClick={() => !past && setSelectedSlot(slot)}
                title={past ? "This time has already passed" : `Select ${time}`}
              >
                {time}
              </button>
            );
          })}
        </div>
      </div>

      {/* Book Appointment button */}
      {selectedSlot && !isSlotPast(selectedSlot.label) && (
        <div className="appt-selected-slot-summary">
          <span className="appt-selected-slot-icon">✓</span>
          <span className="appt-selected-slot-text">
            {doctor.name} · {slotTime(selectedSlot.label)}
            {selectedDate && ` · ${selectedDate.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" })}`}
          </span>
        </div>
      )}
      <button
        type="button"
        className="appt-confirm-btn"
        disabled={disabled || !selectedSlot || isSlotPast(selectedSlot.label)}
        onClick={() => {
          if (selectedSlot && !isSlotPast(selectedSlot.label)) {
            onPick(selectedSlot.message);
          }
        }}
      >
        Book Appointment
        <span className="appt-confirm-icon">📅</span>
      </button>
      <p className="appt-confirm-note">No payment required until the visit.</p>
    </div>
  );
}

// ─── AppointmentConfirmedCard ────────────────────────────────────────────────

function appointmentStatusLabel(status?: ChatUiPayload["status"]): string {
  if (status === "cancelled") return "Cancelled";
  if (status === "rescheduled") return "Rescheduled";
  return "Confirmed";
}

function AppointmentConfirmedCard({
  aptId,
  ui,
  disabled,
  onPick,
}: {
  aptId: string;
  ui: ChatUiPayload;
  disabled?: boolean;
  onPick: (message: string) => void;
}) {
  const [reminderSet, setReminderSet] = useState(Boolean(ui.reminder_set));
  const [reminderPending, setReminderPending] = useState(false);
  const status = ui.status ?? "confirmed";
  const isCancelled = status === "cancelled";
  const isSuperseded = Boolean(ui.actions_disabled);
  const actionsOff = Boolean(disabled || isSuperseded);

  useEffect(() => {
    setReminderSet(Boolean(ui.reminder_set));
    if (ui.reminder_set) setReminderPending(false);
  }, [ui.reminder_set, ui.appointment_id]);

  async function handleReminder() {
    if (reminderSet || isCancelled || actionsOff || reminderPending) return;
    const message = buildSetReminderMessage(aptId, ui.appointment_id);
    setReminderPending(true);
    try {
      await onPick(message);
    } finally {
      setReminderPending(false);
    }
  }

  const headerTitle =
    status === "cancelled"
      ? "Appointment Cancelled"
      : status === "rescheduled"
        ? "Appointment Rescheduled"
        : "Booking Confirmed";

  return (
    <div
      className={[
        "appt-confirmed-card",
        isCancelled ? "appt-confirmed-card--cancelled" : "",
        isSuperseded ? "appt-confirmed-card--superseded" : "",
      ].filter(Boolean).join(" ")}
    >
      <div className="appt-confirmed-header">
        <span className={`appt-confirmed-check appt-confirmed-check--${status}`}>
          {isCancelled ? "✕" : "✓"}
        </span>
        <div className="appt-confirmed-header-text">
          <span className="appt-confirmed-header-title">{headerTitle}</span>
          <span className={`appt-status-badge appt-status-badge--${status}`}>
            {appointmentStatusLabel(status)}
          </span>
        </div>
        <span className="appt-confirmed-apt-id">{aptId}</span>
      </div>

      <div className="appt-confirmed-info">
        {ui.doctor_name && (
          <div className="appt-confirmed-row">
            <span className="appt-confirmed-row-label">Doctor</span>
            <span className="appt-confirmed-row-value">{ui.doctor_name}</span>
          </div>
        )}
        {ui.specialty && (
          <div className="appt-confirmed-row">
            <span className="appt-confirmed-row-label">Specialization</span>
            <span className="appt-confirmed-row-value">{ui.specialty}</span>
          </div>
        )}
        {ui.label && (
          <div className="appt-confirmed-row">
            <span className="appt-confirmed-row-label">Date &amp; Time</span>
            <span className="appt-confirmed-row-value">{ui.label}</span>
          </div>
        )}
        {ui.hospital_name && (
          <div className="appt-confirmed-row">
            <span className="appt-confirmed-row-label">Hospital / Clinic</span>
            <span className="appt-confirmed-row-value">{ui.hospital_name}</span>
          </div>
        )}
        <div className="appt-confirmed-row">
          <span className="appt-confirmed-row-label">Appointment ID</span>
          <span className="appt-confirmed-row-value appt-confirmed-id-val">{aptId}</span>
        </div>
      </div>

      {!isCancelled && (
        <div className="appt-confirmed-actions">
          <button
            type="button"
            className={`appt-confirmed-btn appt-confirmed-btn--reminder${reminderSet ? " appt-confirmed-btn--reminder-set" : ""}`}
            disabled={actionsOff || reminderSet || reminderPending}
            onClick={() => void handleReminder()}
            title={
              reminderSet
                ? "Reminder already set for 30 min before"
                : reminderPending
                  ? "Scheduling reminder..."
                  : "Set a 30-min reminder"
            }
          >
            <span className="appt-confirmed-btn-icon">🔔</span>
            {reminderSet ? "Reminder Set" : reminderPending ? "Setting..." : "Set Reminder"}
          </button>

          <button
            type="button"
            className="appt-confirmed-btn appt-confirmed-btn--reschedule"
            disabled={actionsOff}
            onClick={() => onPick(buildRescheduleAppointmentMessage(aptId))}
            title="Reschedule this appointment"
          >
            <span className="appt-confirmed-btn-icon">🔄</span>
            Reschedule
          </button>

          <button
            type="button"
            className="appt-confirmed-btn appt-confirmed-btn--cancel"
            disabled={actionsOff}
            onClick={() => onPick(buildCancelAppointmentMessage(aptId))}
            title="Cancel this appointment"
          >
            <span className="appt-confirmed-btn-icon">✕</span>
            Cancel Appointment
          </button>
        </div>
      )}

      <p className="appt-confirmed-note">
        {isCancelled
          ? "This appointment is cancelled. The record is kept here for your reference."
          : isSuperseded
            ? "This is a previous version of your appointment. Use the latest card below to manage it."
            : "Use the buttons above to manage your appointment anytime."}
      </p>
    </div>
  );
}

// ─── UrgentConsultCard ───────────────────────────────────────────────────────

interface UrgentDoctorRow {
  id: string;
  name: string;
  specialty?: string;
  offer_status?: string;
}

function UrgentConsultCard({ ui }: { ui: ChatUiPayload }) {
  const [live, setLive] = useState(ui);
  const [waitSeconds, setWaitSeconds] = useState(0);

  useEffect(() => {
    setLive(ui);
    setWaitSeconds(0);
  }, [ui.request_id, ui.type, ui.join_url, ui.doctor_name]);

  useEffect(() => {
    if (live.type === "urgent_consult_accepted" || live.join_url) return;
    const tick = window.setInterval(() => setWaitSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(tick);
  }, [live.type, live.join_url]);

  useEffect(() => {
    if (!live.request_id || live.type === "urgent_consult_accepted" || live.join_url) return;
    let active = true;
    const poll = async () => {
      try {
        const data = await api<{
          id: string;
          status: string;
          accepted_doctor_name?: string;
          appointment_id?: string;
          join_url?: string;
          specialty?: string;
          symptoms?: string[];
        }>(`/api/v1/urgent-consult/requests/${live.request_id}`);
        if (!active) return;
        if (data.status === "assigned") {
          setLive((prev) => ({
            ...prev,
            type: "urgent_consult_accepted",
            doctor_name: data.accepted_doctor_name,
            appointment_id: data.appointment_id,
            join_url: data.join_url,
            specialty: data.specialty,
            symptoms: data.symptoms,
          }));
        }
      } catch {
        /* polling handled by interval */
      }
    };
    void poll();
    const timer = window.setInterval(poll, 4000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [live.request_id, live.type, live.join_url]);

  const accepted = live.type === "urgent_consult_accepted" || Boolean(live.join_url);
  const doctors = (live.doctors ?? []) as UrgentDoctorRow[];
  const symptoms = (live.symptoms ?? []).filter(Boolean);
  const specialty = live.specialty || "General Physician";
  const waitLabel =
    waitSeconds < 60
      ? `${waitSeconds}s`
      : `${Math.floor(waitSeconds / 60)}m ${waitSeconds % 60}s`;

  const steps = [
    { label: "Request sent", done: true },
    { label: "Doctors notified", done: doctors.length > 0 || accepted },
    { label: "Doctor accepts", done: accepted },
    { label: "Video consult", done: accepted && Boolean(live.join_url) },
  ];

  return (
    <div className={`patient-urgent-card${accepted ? " patient-urgent-card--accepted" : ""}`}>
      {!accepted && (
        <div className="patient-urgent-er" role="note">
          <span className="material-symbols-outlined" aria-hidden>
            e911_emergency
          </span>
          <p>
            If you have severe breathing difficulty, chest pain, or feel unsafe,{" "}
            <strong>call emergency services (911) or go to the ER now</strong> — do not wait.
          </p>
        </div>
      )}

      <div className="patient-urgent-hero">
        <div className={`patient-urgent-icon${accepted ? " patient-urgent-icon--success" : ""}`}>
          <span className="material-symbols-outlined">{accepted ? "videocam" : "emergency"}</span>
          {!accepted && <span className="patient-urgent-pulse" aria-hidden />}
        </div>
        <div className="patient-urgent-hero-text">
          <span className="patient-urgent-kicker">
            {accepted ? "Doctor connected" : "Urgent video consult"}
          </span>
          <strong>
            {accepted
              ? `${live.doctor_name || "Your doctor"} is ready for you`
              : "We're connecting you with a doctor"}
          </strong>
          <p>
            {accepted
              ? "Join the secure video room below. Keep this tab open."
              : `${specialty} doctors have been alerted. The first available doctor will accept your request.`}
          </p>
        </div>
      </div>

      {symptoms.length > 0 && (
        <div className="patient-urgent-symptoms">
          <span className="patient-urgent-symptoms-label">Your reported symptoms</span>
          <div className="patient-urgent-symptom-tags">
            {symptoms.map((symptom) => (
              <span key={symptom} className="patient-urgent-symptom-tag">
                {symptom}
              </span>
            ))}
          </div>
        </div>
      )}

      <ol className="patient-urgent-steps" aria-label="Consult progress">
        {steps.map((step, index) => (
          <li
            key={step.label}
            className={`patient-urgent-step${step.done ? " patient-urgent-step--done" : ""}${
              !step.done && steps[index - 1]?.done ? " patient-urgent-step--active" : ""
            }`}
          >
            <span className="patient-urgent-step-dot" aria-hidden>
              {step.done ? (
                <span className="material-symbols-outlined">check</span>
              ) : (
                <span>{index + 1}</span>
              )}
            </span>
            <span>{step.label}</span>
          </li>
        ))}
      </ol>

      {!accepted && doctors.length > 0 && (
        <div className="patient-urgent-doctors">
          <span className="patient-urgent-doctors-label">
            Notified doctors ({doctors.length})
          </span>
          <ul>
            {doctors.map((doc) => (
              <li key={doc.id}>
                <DoctorAvatar
                  name={doc.name}
                  className="patient-urgent-doctor-avatar"
                  initialsClassName="patient-urgent-doctor-avatar patient-urgent-doctor-avatar--initials"
                />
                <div>
                  <strong>{doc.name}</strong>
                  <span>{doc.specialty || specialty}</span>
                </div>
                <span className="patient-urgent-doctor-status">
                  {doc.offer_status === "superseded" ? "Assigned elsewhere" : "Notified"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {accepted && live.doctor_name && (
        <div className="patient-urgent-doctor-ready">
          <DoctorAvatar
            name={live.doctor_name}
            className="patient-urgent-doctor-avatar patient-urgent-doctor-avatar--lg"
            initialsClassName="patient-urgent-doctor-avatar patient-urgent-doctor-avatar--lg patient-urgent-doctor-avatar--initials"
          />
          <div>
            <strong>{live.doctor_name}</strong>
            <span>{specialty}</span>
            {live.apt_id && <span className="patient-urgent-apt">Appointment {live.apt_id}</span>}
          </div>
        </div>
      )}

      {accepted && live.join_url ? (
        <a
          href={live.join_url}
          target="_blank"
          rel="noopener noreferrer"
          className="patient-urgent-join-btn"
        >
          <span className="material-symbols-outlined">videocam</span>
          Join video consultation now
        </a>
      ) : (
        <div className="patient-urgent-waiting" aria-live="polite">
          <div className="patient-urgent-waiting-dots" aria-hidden>
            <span />
            <span />
            <span />
          </div>
          <div>
            <strong>Waiting for a doctor to accept</strong>
            <span>Usually within a few minutes · waiting {waitLabel}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── ChoiceButtons ───────────────────────────────────────────────────────────

function ChoiceButtons({
  options,
  disabled,
  onPick,
  variant = "pill",
  ctaMode = false,
}: {
  options: ChoiceOption[];
  disabled?: boolean;
  onPick: (message: string) => void;
  variant?: "pill" | "stack";
  ctaMode?: boolean;
}) {
  function chipClass(label: string): string {
    if (!ctaMode) return "chat-choice-chip";
    const isPrimary = /book/i.test(label);
    return `chat-choice-chip ${isPrimary ? "chat-choice-chip--primary" : "chat-choice-chip--secondary"}`;
  }

  function displayLabel(label: string): string {
    if (!ctaMode) return label;
    if (/book appointment/i.test(label)) return `📅 ${label}`;
    if (/self-care/i.test(label)) return `💡 ${label}`;
    if (/explain/i.test(label)) return `📄 ${label}`;
    return label;
  }

  return (
    <div className={`chat-choice-grid ${variant === "stack" ? "chat-choice-grid--stack" : ""}`}>
      {options.map((opt) => (
        <button
          key={opt.label}
          type="button"
          className={chipClass(opt.label)}
          disabled={disabled}
          onClick={() => onPick(opt.message)}
        >
          {displayLabel(opt.label)}
        </button>
      ))}
    </div>
  );
}

// ─── SlotButtons (fallback for slot_list type) ───────────────────────────────

function SlotButtons({
  slots,
  disabled,
  onPick,
  compact,
  chipClassName = "chat-slot-chip",
}: {
  slots: SlotUi[];
  disabled?: boolean;
  onPick: (message: string) => void;
  compact?: boolean;
  chipClassName?: string;
}) {
  const bookable = useMemo(() => filterChatBookableSlots(slots), [slots]);
  const groups = groupSlots(bookable);
  return (
    <div className={`chat-slot-groups ${compact ? "chat-slot-groups--compact" : ""}`}>
      {groups.map((g) => (
        <div key={g.day} className="chat-slot-day-group">
          <span className="chat-slot-day-label">{g.day}</span>
          <div className="chat-slot-grid">
            {g.items.map((slot, i) => (
              <button
                key={`${slot.label}-${i}`}
                type="button"
                className={chipClassName}
                disabled={disabled}
                onClick={() => onPick(slot.message)}
                title={`Book ${slot.label}`}
              >
                {slotTime(slot.label)}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─── RescheduleSlotCard ───────────────────────────────────────────────────────

function RescheduleSlotCard({
  ui,
  disabled,
  onPick,
}: {
  ui: ChatUiPayload;
  disabled?: boolean;
  onPick: (message: string) => void;
}) {
  const slots = ui.slots ?? [];
  const bookableSlots = useMemo(() => filterChatBookableSlots(slots), [slots]);
  const aptId = ui.apt_id ?? "";
  const doctorName = ui.doctor_name ?? "Doctor";
  const currentTime = ui.current_time ?? ui.current ?? "";

  return (
    <div className="reschedule-card reschedule-card--compact">
      <div className="reschedule-card-header">
        <span className="reschedule-card-header-icon" aria-hidden="true">
          <span className="material-symbols-outlined">event_repeat</span>
        </span>
        <div className="reschedule-card-header-text">
          <span className="reschedule-card-title">Reschedule</span>
          {aptId && <span className="reschedule-card-apt-id">{aptId}</span>}
        </div>
      </div>

      <div className="reschedule-card-body">
        <dl className="reschedule-card-facts">
          <div className="reschedule-card-fact">
            <dt>Doctor</dt>
            <dd>{doctorName}</dd>
          </div>
          {currentTime && (
            <div className="reschedule-card-fact reschedule-card-fact--current">
              <dt>Current</dt>
              <dd>{currentTime}</dd>
            </div>
          )}
        </dl>

        <div className="reschedule-card-slots">
          <div className="reschedule-card-slots-head">
            <span className="reschedule-card-slots-title">New time</span>
            <span className="reschedule-card-slots-badge">{bookableSlots.length} open</span>
          </div>
          {bookableSlots.length > 0 ? (
            <SlotButtons
              slots={bookableSlots}
              disabled={disabled}
              onPick={onPick}
              compact
              chipClassName="reschedule-slot-chip"
            />
          ) : (
            <p className="reschedule-card-empty">No later slots today. Try tomorrow or check back soon.</p>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── RescheduleConfirmCard ────────────────────────────────────────────────────

function RescheduleConfirmCard({
  ui,
  disabled,
  onPick,
}: {
  ui: ChatUiPayload;
  disabled?: boolean;
  onPick: (message: string) => void;
}) {
  return (
    <div className="reschedule-confirm-card">
      <div className="reschedule-confirm-header">
        <span className="reschedule-confirm-header-icon" aria-hidden="true">
          <span className="material-symbols-outlined">published_with_changes</span>
        </span>
        <span className="reschedule-confirm-title">Confirm New Time</span>
      </div>
      <div className="reschedule-confirm-details">
        {ui.current && (
          <div className="reschedule-confirm-row">
            <span className="reschedule-confirm-label">Current</span>
            <span className="reschedule-confirm-value">{ui.current}</span>
          </div>
        )}
        {ui.label && (
          <div className="reschedule-confirm-row reschedule-confirm-row--new">
            <span className="reschedule-confirm-label">New time</span>
            <span className="reschedule-confirm-value">{ui.label}</span>
          </div>
        )}
      </div>
      <div className="reschedule-confirm-actions">
        {ui.options?.map((opt) => {
          const isConfirm = opt.message.toLowerCase() === "yes";
          return (
            <button
              key={opt.label}
              type="button"
              className={`reschedule-confirm-btn ${isConfirm ? "reschedule-confirm-btn--yes" : "reschedule-confirm-btn--no"}`}
              disabled={disabled}
              onClick={() => onPick(opt.message)}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ─── Main ChatBookingUI export ───────────────────────────────────────────────

export function ChatBookingUI({ ui, disabled, onPick }: Props) {
  const [activeDoctorId, setActiveDoctorId] = useState<string | null>(null);

  // ── confirm_booking ──
  if (ui.type === "confirm_booking" && ui.options?.length) {
    return (
      <div className="confirm-booking-card">
        <div className="confirm-booking-header">
          <span className="confirm-booking-icon">📋</span>
          <span className="confirm-booking-title">Confirm Your Appointment</span>
        </div>
        <div className="confirm-booking-details">
          {ui.patient_name && (
            <div className="confirm-booking-row">
              <span className="confirm-booking-label">👤 Patient</span>
              <span className="confirm-booking-value">{ui.patient_name}</span>
            </div>
          )}
          {ui.doctor_name && (
            <div className="confirm-booking-row">
              <span className="confirm-booking-label">🩺 Doctor</span>
              <span className="confirm-booking-value">{ui.doctor_name}</span>
            </div>
          )}
          {ui.label && (
            <div className="confirm-booking-row">
              <span className="confirm-booking-label">📅 Date & Time</span>
              <span className="confirm-booking-value">{ui.label}</span>
            </div>
          )}
        </div>
        <div className="confirm-booking-actions">
          {ui.options.map((opt) => (
            <button
              key={opt.label}
              type="button"
              className={`confirm-booking-btn ${opt.message.toLowerCase() === "yes" ? "confirm-booking-btn--yes" : "confirm-booking-btn--no"}`}
              disabled={disabled}
              onClick={() => onPick(opt.message)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>
    );
  }

  // ── confirm_reschedule ──
  if (ui.type === "confirm_reschedule" && ui.options?.length) {
    return <RescheduleConfirmCard ui={ui} disabled={disabled} onPick={onPick} />;
  }

  // ── reschedule_slots ──
  if (ui.type === "reschedule_slots" && ui.slots?.length) {
    return <RescheduleSlotCard ui={ui} disabled={disabled} onPick={onPick} />;
  }

  // ── urgent_consult ──
  if (
    (ui.type === "urgent_consult_pending" || ui.type === "urgent_consult_accepted") &&
    ui.request_id
  ) {
    return <UrgentConsultCard ui={ui} />;
  }

  // ── video_consultation ──
  if (ui.type === "video_consultation" && ui.join_url) {
    return (
      <div className="video-consult-card">
        <div className="video-consult-card-header">
          <span>📹</span>
          <div>
            <strong>Video consultation ready</strong>
            {ui.doctor_name && <p>with {ui.doctor_name}</p>}
            {ui.apt_id && <p className="video-consult-apt">{ui.apt_id}</p>}
          </div>
        </div>
        <a
          href={ui.join_url}
          target="_blank"
          rel="noopener noreferrer"
          className="video-consult-join-btn"
        >
          Join Video Call
        </a>
        {ui.options?.map((opt) =>
          opt.message.toLowerCase() === "not now" ? (
            <button
              key={opt.label}
              type="button"
              className="chat-choice-chip"
              disabled={disabled}
              onClick={() => onPick(opt.message)}
            >
              {opt.label}
            </button>
          ) : null
        )}
      </div>
    );
  }

  // ── follow-up action menus (self-care, book, report) ──
  if (
    (ui.type === "post_assessment" || ui.type === "report_followup") &&
    ui.options?.length
  ) {
    return (
      <div className="chat-choice-panel chat-choice-panel--followup">
        <ChoiceButtons
          options={ui.options}
          disabled={disabled}
          onPick={onPick}
          variant="stack"
          ctaMode
        />
      </div>
    );
  }

  // ── choice menus (symptoms, duration, nav, etc.) ──
  if (CHOICE_MENU_TYPES.has(ui.type) && ui.options?.length) {
    return (
      <div className="chat-booking-panel chat-choice-panel">
        <ChoiceButtons
          options={ui.options}
          disabled={disabled}
          onPick={onPick}
          variant={ui.variant === "stack" ? "stack" : "pill"}
        />
      </div>
    );
  }

  // ── appointment_confirmed ──
  if (ui.type === "appointment_confirmed" && ui.appointment_id) {
    const aptId = ui.apt_id || ui.appointment_id;
    return <AppointmentConfirmedCard aptId={aptId} ui={ui} disabled={disabled} onPick={onPick} />;
  }

  // ── slot_list (single doctor, slot chips only) ──
  if (ui.type === "slot_list" && ui.slots?.length) {
    return (
      <div className="chat-booking-panel">
        <div className="chat-booking-header">
          <div className="chat-booking-header-text">
            <span className="chat-booking-title">{ui.doctor_name ?? "Doctor"}</span>
            <span className="chat-booking-subtitle">Tap a time to book</span>
          </div>
          <span className="chat-booking-badge">{ui.slots.length} open</span>
        </div>
        <SlotButtons slots={ui.slots} disabled={disabled} onPick={onPick} />
      </div>
    );
  }

  // ── doctor_list — two-column booking panel ──
  if (ui.type === "doctor_list" && ui.doctors?.length) {
    const doctorsWithSlots = ui.doctors.filter((d) => (d.slots?.length ?? 0) > 0);

    const resolvedId = activeDoctorId ?? doctorsWithSlots[0]?.id;
    const activeDoctor =
      ui.doctors.find((d) => d.id === resolvedId) ?? doctorsWithSlots[0];

    if (!activeDoctor) return null;

    return (
      <div className="medai-booking-panel">
        {/* Left: doctor list */}
        <div className="medai-doctor-col">
          <div className="medai-section-label">Available Doctors</div>

          {doctorsWithSlots.map((doc) => {
            const isActive = doc.id === resolvedId;
            return (
              <button
                key={doc.id}
                type="button"
                className={["medai-doc-card", isActive ? "medai-doc-card--active" : ""].filter(Boolean).join(" ")}
                disabled={disabled}
                onClick={() => setActiveDoctorId(doc.id)}
              >
                <div className="medai-doc-avatar-wrap">
                  <DoctorAvatar
                    name={doc.name}
                    profileImageUrl={doc.profile_image_url}
                    className="medai-doc-avatar medai-doc-avatar--photo"
                    initialsClassName="medai-doc-avatar"
                  />
                </div>
                <div className="medai-doc-info">
                  <span className="medai-doc-name">{doc.name}</span>
                  <span className="medai-doc-meta">{doc.specialty}</span>
                  {doc.professional_summary && (
                    <span className="medai-doc-summary">{doc.professional_summary}</span>
                  )}
                  <div className="medai-doc-stats">
                    {doc.experience_years > 0 && (
                      <span className="medai-doc-stat">
                        <span className="medai-stat-icon">⏱</span>
                        {doc.experience_years}+ Yrs
                      </span>
                    )}
                    {doc.consultation_fee != null && (
                      <span className="medai-doc-stat">
                        <span className="medai-stat-icon">₹</span>
                        {doc.consultation_fee}
                      </span>
                    )}
                    {doc.next_available && (
                      <span className="medai-doc-stat">
                        <span className="medai-stat-icon">📅</span>
                        {doc.next_available}
                      </span>
                    )}
                  </div>
                </div>
                {doc.rating != null && (
                  <span className="medai-doc-rating">★ {doc.rating}</span>
                )}
              </button>
            );
          })}
        </div>

        {/* Right: full calendar + slot picker */}
        <div className="medai-picker-col">
          <AppointmentPicker
            key={activeDoctor.id}
            doctor={activeDoctor}
            slots={activeDoctor.slots ?? []}
            disabled={disabled}
            onPick={onPick}
          />
        </div>
      </div>
    );
  }

  return null;
}

// ─── formatChatText helper ───────────────────────────────────────────────────

export function formatChatText(text: string): ReactNode {
  const parts = text.split(/(\*\*[^*\n]+\*\*|\*[^*\n]+\*|_[^_\n]+_)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <strong key={i}>{part.slice(1, -1)}</strong>;
    }
    if (part.startsWith("_") && part.endsWith("_") && part.length > 2) {
      return <em key={i}>{part.slice(1, -1)}</em>;
    }
    return <span key={i}>{part}</span>;
  });
}
