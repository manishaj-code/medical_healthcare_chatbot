import {
  filterBookableSlots,
  formatDoctorTime,
  groupSlotsByDate,
  type DoctorSlot,
} from "../../utils/doctorPortal";

interface Props {
  slots: DoctorSlot[];
  onSeedSlots?: () => void;
  seeding?: boolean;
}

export default function DoctorAvailabilityGrid({ slots, onSeedSlots, seeding }: Props) {
  const bookableSlots = filterBookableSlots(slots);
  const byDay = groupSlotsByDate(slots);
  const totalDays = byDay.length;
  const todaySlots = byDay.find((d) => d.isToday)?.times.length ?? 0;
  const firstDate = byDay[0]?.displayDate;
  const lastDate = byDay[byDay.length - 1]?.displayDate;

  return (
    <div className="dp-availability">
      <div className="dp-availability-stats">
        <div className="dp-availability-stat">
          <span className="material-symbols-outlined">event_available</span>
          <div>
            <p className="dp-availability-stat-value">{bookableSlots.length}</p>
            <p className="dp-availability-stat-label">Open slots</p>
          </div>
        </div>
        <div className="dp-availability-stat">
          <span className="material-symbols-outlined">date_range</span>
          <div>
            <p className="dp-availability-stat-value">{totalDays}</p>
            <p className="dp-availability-stat-label">Days scheduled</p>
          </div>
        </div>
        <div className="dp-availability-stat">
          <span className="material-symbols-outlined">today</span>
          <div>
            <p className="dp-availability-stat-value">{todaySlots}</p>
            <p className="dp-availability-stat-label">Slots today</p>
          </div>
        </div>
      </div>

      {firstDate && lastDate && (
        <p className="dp-availability-range">
          <span className="material-symbols-outlined">info</span>
          Showing availability from <strong>{firstDate}</strong> through <strong>{lastDate}</strong>.
          Patients can book any open time via chatbot or the Doctors page.
        </p>
      )}

      <div className="dp-availability-days">
        {byDay.map((day) => (
          <div
            key={day.date}
            className={`dp-availability-day${day.isToday ? " dp-availability-day--today" : ""}`}
          >
            <header className="dp-availability-day-head">
              <div className="dp-availability-day-date">
                {day.isToday && <span className="dp-availability-today-badge">Today</span>}
                <h3>{day.weekday}</h3>
                <span className="dp-availability-day-cal">{day.displayDate}</span>
              </div>
              <span className="dp-availability-day-count">
                {day.times.length} slot{day.times.length !== 1 ? "s" : ""}
              </span>
            </header>
            <div className="dp-availability-times">
              {day.times.map((time) => (
                <span key={`${day.date}-${time}`} className="dp-slot-time">
                  <span className="material-symbols-outlined">schedule</span>
                  {formatDoctorTime(time)}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {onSeedSlots && (
        <div className="dp-availability-foot">
          <button type="button" className="dp-btn dp-btn--outline dp-btn--sm" onClick={onSeedSlots} disabled={seeding}>
            <span className="material-symbols-outlined">refresh</span>
            Refresh 14-day schedule
          </button>
        </div>
      )}
    </div>
  );
}
