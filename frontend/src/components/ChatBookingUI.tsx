import { useState } from "react";
import type { ReactNode } from "react";

interface SlotUi {
  label: string;
  doctor_id: string;
  doctor_name: string;
  message: string;
}

interface DoctorUi {
  id: string;
  name: string;
  specialty: string;
  experience_years: number;
  rating: number | null;
  slots: SlotUi[];
}

export interface ChoiceOption {
  label: string;
  message: string;
}

export interface ChatUiPayload {
  type:
    | "doctor_list"
    | "slot_list"
    | "appointment_confirmed"
    | "confirm_booking"
    | "confirm_reschedule"
    | "yes_no"
    | "symptom_picker"
    | "duration_picker"
    | "severity_picker";
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
  options?: ChoiceOption[];
}

interface Props {
  ui: ChatUiPayload;
  disabled?: boolean;
  onPick: (message: string) => void;
}

function doctorInitials(name: string): string {
  const parts = name.replace(/^Dr\.?\s*/i, "").trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (parts[0]?.[0] ?? "D").toUpperCase();
}

function slotDay(label: string): string {
  const idx = label.indexOf(":");
  return idx > 0 ? label.slice(0, idx).trim() : "Other";
}

function slotTime(label: string): string {
  const idx = label.indexOf(":");
  return idx > 0 ? label.slice(idx + 1).trim() : label;
}

function groupSlots(slots: SlotUi[]): { day: string; items: SlotUi[] }[] {
  const map = new Map<string, SlotUi[]>();
  for (const slot of slots) {
    const day = slotDay(slot.label);
    if (!map.has(day)) map.set(day, []);
    map.get(day)!.push(slot);
  }
  return Array.from(map.entries()).map(([day, items]) => ({ day, items }));
}

function ChoiceButtons({
  options,
  disabled,
  onPick,
  variant = "pill",
}: {
  options: ChoiceOption[];
  disabled?: boolean;
  onPick: (message: string) => void;
  variant?: "pill" | "stack";
}) {
  return (
    <div className={`chat-choice-grid ${variant === "stack" ? "chat-choice-grid--stack" : ""}`}>
      {options.map((opt) => (
        <button
          key={opt.label}
          type="button"
          className="chat-choice-chip"
          disabled={disabled}
          onClick={() => onPick(opt.message)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

function SlotButtons({
  slots,
  disabled,
  onPick,
  compact,
}: {
  slots: SlotUi[];
  disabled?: boolean;
  onPick: (message: string) => void;
  compact?: boolean;
}) {
  const groups = groupSlots(slots);
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
                className="chat-slot-chip"
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

export function ChatBookingUI({ ui, disabled, onPick }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (ui.type === "confirm_booking" && ui.options?.length) {
    return (
      <div className="chat-booking-panel chat-confirm-panel">
        <div className="chat-confirm-details">
          {ui.patient_name && (
            <p><strong>Patient:</strong> {ui.patient_name}</p>
          )}
          {ui.doctor_name && (
            <p><strong>Doctor:</strong> {ui.doctor_name}</p>
          )}
          {ui.label && (
            <p><strong>Date & Time:</strong> {ui.label}</p>
          )}
        </div>
        <ChoiceButtons options={ui.options} disabled={disabled} onPick={onPick} variant="stack" />
      </div>
    );
  }

  if (ui.type === "confirm_reschedule" && ui.options?.length) {
    return (
      <div className="chat-booking-panel chat-confirm-panel">
        <div className="chat-confirm-details">
          {ui.current && <p><strong>Current:</strong> {ui.current}</p>}
          {ui.label && <p><strong>New time:</strong> {ui.label}</p>}
        </div>
        <ChoiceButtons options={ui.options} disabled={disabled} onPick={onPick} variant="stack" />
      </div>
    );
  }

  if (
    (ui.type === "yes_no" ||
      ui.type === "symptom_picker" ||
      ui.type === "duration_picker" ||
      ui.type === "severity_picker") &&
    ui.options?.length
  ) {
    return (
      <div className="chat-booking-panel chat-choice-panel">
        <ChoiceButtons options={ui.options} disabled={disabled} onPick={onPick} />
      </div>
    );
  }

  if (ui.type === "appointment_confirmed" && ui.appointment_id) {
    const aptId = ui.apt_id || ui.appointment_id;
    return (
      <div className="chat-booking-panel chat-appt-confirmed">
        <div className="chat-appt-confirmed-row">
          <div className="chat-appt-confirmed-details">
            <span className="chat-booking-title">Appointment confirmed</span>
            <span className="chat-booking-subtitle">
              {ui.doctor_name} · {ui.label}
            </span>
            <span className="chat-appt-id">{aptId}</span>
          </div>
          <div className="chat-appt-actions chat-appt-actions--inline">
            <button
              type="button"
              className="btn btn-outline chat-appt-btn chat-appt-btn--reminder"
              disabled={disabled}
              onClick={() => onPick(`Set a reminder 30 minutes before appointment ${aptId}`)}
            >
              Reminder
            </button>
            <button
              type="button"
              className="btn btn-outline chat-appt-btn chat-appt-btn--reschedule"
              disabled={disabled}
              onClick={() => onPick(`I want to reschedule my appointment ${aptId}`)}
            >
              Reschedule
            </button>
            <button
              type="button"
              className="btn btn-danger chat-appt-btn chat-appt-btn--cancel"
              disabled={disabled}
              onClick={() => onPick(`Please cancel my appointment ${aptId}`)}
            >
              Cancel
            </button>
          </div>
        </div>
      </div>
    );
  }

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

  if (ui.type === "doctor_list" && ui.doctors?.length) {
    const total = ui.total ?? ui.doctors.length;
    return (
      <div className="chat-booking-panel">
        <div className="chat-booking-header">
          <div className="chat-booking-header-text">
            <span className="chat-booking-title">Available Doctors</span>
            <span className="chat-booking-subtitle">Tap a doctor or time to book</span>
          </div>
          <span className="chat-booking-badge">{total} doctors</span>
        </div>

        <div className="chat-doctor-list">
          {ui.doctors.map((doc) => {
            const expanded = expandedId === doc.id;
            const nextSlot = doc.slots?.[0]?.label;
            return (
              <div
                key={doc.id}
                className={`chat-doctor-card ${expanded ? "chat-doctor-card--expanded" : ""}`}
              >
                <div className="chat-doctor-card-top">
                  <div className="chat-doctor-avatar">{doctorInitials(doc.name)}</div>
                  <button
                    type="button"
                    className="chat-doctor-info"
                    disabled={disabled}
                    onClick={() => {
                      setExpandedId(expanded ? null : doc.id);
                    }}
                  >
                    <span className="chat-doctor-name">{doc.name}</span>
                    <span className="chat-doctor-meta">
                      {doc.specialty}
                      {doc.experience_years > 0 && ` · ${doc.experience_years} yrs`}
                    </span>
                  </button>
                  <div className="chat-doctor-badges">
                    {doc.rating != null && (
                      <span className="chat-rating-badge">★ {doc.rating}</span>
                    )}
                    {nextSlot && !expanded && (
                      <span className="chat-next-badge">{slotTime(nextSlot)}</span>
                    )}
                  </div>
                </div>

                <div className="chat-doctor-actions">
                  <button
                    type="button"
                    className="btn btn-outline chat-select-doctor-btn"
                    disabled={disabled}
                    onClick={() => onPick(doc.name)}
                  >
                    Select doctor
                  </button>
                  {(doc.slots?.length ?? 0) > 0 && (
                    <button
                      type="button"
                      className="chat-toggle-slots"
                      disabled={disabled}
                      onClick={() => setExpandedId(expanded ? null : doc.id)}
                    >
                      {expanded ? "Hide times" : `View ${doc.slots?.length ?? 0} slots`}
                    </button>
                  )}
                </div>

                {expanded && (doc.slots?.length ?? 0) > 0 && (
                  <div className="chat-doctor-slots">
                    <SlotButtons slots={doc.slots ?? []} disabled={disabled} onPick={onPick} compact />
                  </div>
                )}

                {!expanded && (doc.slots?.length ?? 0) === 0 && (
                  <p className="chat-doctor-no-slots">No open slots</p>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return null;
}

export function formatChatText(text: string): ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*|_[^_]+_)/g);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("_") && part.endsWith("_")) {
      return <em key={i}>{part.slice(1, -1)}</em>;
    }
    return <span key={i}>{part}</span>;
  });
}
