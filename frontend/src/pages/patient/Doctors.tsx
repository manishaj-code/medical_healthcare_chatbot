import { useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import {
  buildBannerCopy,
  clearStaleRecommendationCache,
  resolveRecommendedFromHistory,
  type HistoryRecommendation,
} from "../../utils/recommendedSpecialty";

interface Slot {
  doctor_id: string;
  doctor_name: string;
  slot_date: string;
  slot_time: string;
  label: string;
}

interface Doctor {
  id: string;
  name: string;
  specialty: string;
  experience_years: number;
  rating: number;
  slots: Slot[];
  next_available: string;
}

interface Specialization {
  id: string;
  name: string;
}

const SPECIALTY_ICONS: Record<string, string> = {
  Cardiologist: "cardiology",
  Neurologist: "neurology",
  Dermatologist: "dermatology",
  Pediatrician: "child_care",
  "General Physician": "stethoscope",
  Gastroenterologist: "gastroenterology",
  Emergency: "emergency",
};

function doctorInitials(name: string): string {
  const parts = name.replace(/^Dr\.?\s*/i, "").trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (parts[0]?.[0] ?? "D").toUpperCase();
}

function formatSlotTime(iso: string): string {
  const [h, m] = iso.split(":").map(Number);
  const hour = h % 12 || 12;
  const ampm = h < 12 ? "AM" : "PM";
  return `${hour}:${String(m).padStart(2, "0")} ${ampm}`;
}

function dayLabel(iso: string): string {
  const d = new Date(iso + "T12:00:00");
  const today = new Date();
  today.setHours(12, 0, 0, 0);
  const diff = Math.round((d.getTime() - today.getTime()) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  return d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}

interface AvailabilityRow {
  date: string;
  time: string;
  status: string;
}

const WEEKDAYS = ["M", "T", "W", "T", "F", "S", "S"];

function localDateKey(d = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function toDateKey(year: number, month: number, day: number): string {
  return `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function availabilityToSlots(rows: AvailabilityRow[], doctor: Doctor): Slot[] {
  return rows
    .filter((r) => r.status === "available")
    .map((r) => ({
      doctor_id: doctor.id,
      doctor_name: doctor.name,
      slot_date: r.date,
      slot_time: r.time.length >= 5 ? r.time.slice(0, 5) : r.time,
      label: `${dayLabel(r.date)}: ${formatSlotTime(r.time)}`,
    }));
}

function buildCalendarCells(
  year: number,
  month: number,
  availableDates: Set<string>,
  todayKey: string
): { key: string; day: number | null; available: boolean; past: boolean }[] {
  const first = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0).getDate();
  let startPad = first.getDay() - 1;
  if (startPad < 0) startPad = 6;

  const cells: { key: string; day: number | null; available: boolean; past: boolean }[] = [];
  for (let i = 0; i < startPad; i++) {
    cells.push({ key: `pad-${year}-${month}-${i}`, day: null, available: false, past: false });
  }
  for (let day = 1; day <= lastDay; day++) {
    const key = toDateKey(year, month, day);
    cells.push({
      key,
      day,
      available: availableDates.has(key),
      past: key < todayKey,
    });
  }
  return cells;
}

export default function PatientDoctors() {
  const [doctors, setDoctors] = useState<Doctor[]>([]);
  const [specialties, setSpecialties] = useState<Specialization[]>([]);
  const [specialty, setSpecialty] = useState("");
  const [historyRec, setHistoryRec] = useState<HistoryRecommendation | null>(null);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [booking, setBooking] = useState(false);
  const [selectedDoctorId, setSelectedDoctorId] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);
  const [doctorSlots, setDoctorSlots] = useState<Slot[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [viewMonth, setViewMonth] = useState(() => {
    const t = new Date();
    return { year: t.getFullYear(), month: t.getMonth() };
  });
  const todayKey = localDateKey();
  const querySpecialty = specialty;

  const load = () => {
    setLoading(true);
    const q = querySpecialty ? `?specialty=${encodeURIComponent(querySpecialty)}` : "";
    api<Doctor[]>(`/api/v1/doctors/with-availability${q}`)
      .then((list) => {
        setDoctors(list);
        const pick = list[0];
        if (pick) {
          setSelectedDoctorId(pick.id);
        } else {
          setSelectedDoctorId(null);
          setSelectedDate(null);
          setSelectedSlot(null);
          setDoctorSlots([]);
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    clearStaleRecommendationCache();
    api<Specialization[]>("/api/v1/doctors/specializations").then(setSpecialties).catch(console.error);
    resolveRecommendedFromHistory()
      .then((rec) => {
        if (rec) {
          setHistoryRec(rec);
          setSpecialty((prev) => prev || rec.bookableSpecialty);
        }
      })
      .catch(console.error)
      .finally(() => setHistoryLoaded(true));
  }, []);

  useEffect(() => {
    if (!historyLoaded) return;
    load();
  }, [specialty, historyLoaded]);

  useEffect(() => {
    if (!selectedDoctorId) {
      setDoctorSlots([]);
      return;
    }
    const doc = doctors.find((d) => d.id === selectedDoctorId);
    if (!doc) return;

    setSlotsLoading(true);
    api<AvailabilityRow[]>(`/api/v1/doctors/${selectedDoctorId}/availability`)
      .then((rows) => {
        const slots = availabilityToSlots(rows, doc);
        setDoctorSlots(slots);
        const first = slots[0];
        if (first) {
          setSelectedDate(first.slot_date);
          setSelectedSlot(first);
          const d = new Date(first.slot_date + "T12:00:00");
          setViewMonth({ year: d.getFullYear(), month: d.getMonth() });
        } else {
          setSelectedDate(null);
          setSelectedSlot(null);
        }
      })
      .catch(console.error)
      .finally(() => setSlotsLoading(false));
  }, [selectedDoctorId, doctors]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return doctors;
    return doctors.filter(
      (d) =>
        d.name.toLowerCase().includes(q) ||
        d.specialty.toLowerCase().includes(q)
    );
  }, [doctors, search]);

  const detectedSymptoms = historyRec?.symptoms ?? [];
  const hasDetectedSymptoms = detectedSymptoms.length > 0;
  const bannerSpecialty = hasDetectedSymptoms
    ? ((historyRec?.specialty ?? specialty) || "General Physician")
    : "";
  const bannerCopy = hasDetectedSymptoms ? buildBannerCopy(historyRec, bannerSpecialty) : "";
  const recommendedSpecialty = bannerSpecialty || "General Physician";

  const matchSpecialty = specialty || historyRec?.bookableSpecialty || "";

  const recommendedDoctors = useMemo(() => {
    const pool = matchSpecialty
      ? filtered.filter((d) => d.specialty === matchSpecialty)
      : [...filtered].sort((a, b) => b.rating - a.rating);
    return pool.slice(0, 3);
  }, [filtered, matchSpecialty]);

  const selectedDoctor = doctors.find((d) => d.id === selectedDoctorId) ?? null;

  const availableDates = useMemo(() => {
    const dates = [...new Set(doctorSlots.map((s) => s.slot_date))];
    return dates.sort();
  }, [doctorSlots]);

  const availableDateSet = useMemo(() => new Set(availableDates), [availableDates]);

  const calendarCells = useMemo(
    () => buildCalendarCells(viewMonth.year, viewMonth.month, availableDateSet, todayKey),
    [viewMonth, availableDateSet, todayKey]
  );

  const slotsForDate = useMemo(() => {
    if (!selectedDate) return [];
    return doctorSlots.filter((s) => s.slot_date === selectedDate);
  }, [doctorSlots, selectedDate]);

  const selectDate = (dateKey: string) => {
    setSelectedDate(dateKey);
    const first = doctorSlots.find((s) => s.slot_date === dateKey) ?? null;
    setSelectedSlot(first);
  };

  const shiftMonth = (delta: number) => {
    setViewMonth((prev) => {
      const d = new Date(prev.year, prev.month + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() };
    });
  };

  const selectDoctor = (doc: Doctor) => {
    setSelectedDoctorId(doc.id);
  };

  const confirmBooking = async () => {
    if (!selectedDoctor || !selectedSlot) return;
    setBooking(true);
    try {
      await api("/api/v1/appointments", {
        method: "POST",
        body: JSON.stringify({
          doctor_id: selectedDoctor.id,
          slot_date: selectedSlot.slot_date,
          slot_time: selectedSlot.slot_time.length === 5 ? `${selectedSlot.slot_time}:00` : selectedSlot.slot_time,
        }),
      });
      alert(`Appointment confirmed with ${selectedDoctor.name} — ${selectedSlot.label}`);
      load();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Booking failed");
    } finally {
      setBooking(false);
    }
  };

  const renderDoctorCard = (d: Doctor, recommended = false) => {
    const active = selectedDoctorId === d.id;
    const badge = d.rating >= 4.7 ? "PRO" : d.experience_years <= 5 ? "NEW" : null;
    return (
      <button
        key={d.id}
        type="button"
        className={`fd-doctor-card${active ? " fd-doctor-card--active" : ""}${recommended ? " fd-doctor-card--rec" : ""}`}
        onClick={() => selectDoctor(d)}
      >
        <div className="fd-doctor-card-inner">
          <div className="fd-doctor-avatar-wrap">
            <div className="fd-doctor-avatar">{doctorInitials(d.name)}</div>
            {badge && <span className="fd-doctor-badge">{badge}</span>}
          </div>
          <div className="fd-doctor-info">
            <div className="fd-doctor-info-top">
              <div>
                <h4>{d.name}</h4>
                <p>
                  {d.specialty}
                  {d.experience_years > 0 && ` · ${d.experience_years}+ Yrs Exp.`}
                </p>
              </div>
              <div className="fd-rating-pill">
                <span className="material-symbols-outlined">star</span>
                {d.rating.toFixed(1)}
              </div>
            </div>
            <div className="fd-doctor-meta">
              <span>
                <span className="material-symbols-outlined">history</span>
                {d.experience_years}+ Yrs Exp.
              </span>
              <span>
                <span className="material-symbols-outlined">schedule</span>
                {d.next_available}
              </span>
              <span className="fd-verified">
                <span className="material-symbols-outlined">verified</span>
                Verified
              </span>
            </div>
            {recommended && <span className="fd-rec-tag">AI Recommended</span>}
          </div>
        </div>
      </button>
    );
  };

  return (
    <div className="fd-page">
      <section className="fd-ai-banner">
        <div className="fd-ai-banner-text">
          <span className="fd-ai-badge">
            <span className="material-symbols-outlined">check_circle</span>
            AI Recommendation
          </span>
          {hasDetectedSymptoms && (
            <>
              <h2>Consult a {bannerSpecialty}</h2>
              <p>{bannerCopy}</p>
            </>
          )}
          <div className="fd-filter-row">
            <select
              value={specialty}
              onChange={(e) => setSpecialty(e.target.value)}
              aria-label="Filter specialty"
            >
              <option value="">All specialties</option>
              {specialties.map((s) => (
                <option key={s.id} value={s.name}>{s.name}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="fd-ai-banner-icon">
          <span className="material-symbols-outlined">
            {SPECIALTY_ICONS[recommendedSpecialty] ?? "medical_services"}
          </span>
        </div>
      </section>

      <div className="fd-main-grid">
        <div className="fd-doctors-col">
          {loading && <p className="fd-muted">Loading doctors...</p>}
          {!loading && filtered.length === 0 && (
            <p className="fd-muted">No doctors with open slots right now.</p>
          )}

          {!loading && recommendedDoctors.length > 0 && (
            <div className="fd-section">
              <div className="fd-section-head">
                <h3>Recommended for You</h3>
              </div>
              <div className="fd-doctor-list">
                {recommendedDoctors.map((d) => renderDoctorCard(d, true))}
              </div>
            </div>
          )}

          {!loading && filtered.length > 0 && (
            <div className="fd-section">
              <div className="fd-section-head">
                <h3>All Specialists</h3>
                <span className="fd-count">{filtered.length} available</span>
              </div>
              <div className="fd-search-wrap">
                <span className="material-symbols-outlined">search</span>
                <input
                  type="search"
                  placeholder="Search doctors, clinics..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
              <div className="fd-doctor-list">
                {filtered.map((d) =>
                  renderDoctorCard(d, recommendedDoctors.some((r) => r.id === d.id))
                )}
              </div>
            </div>
          )}

        </div>

        <aside className="fd-booking-panel">
          <h3>Select Appointment</h3>
          {selectedDoctor ? (
            <>
              <p className="fd-selected-doc">
                <strong>{selectedDoctor.name}</strong>
                <span>{selectedDoctor.specialty}</span>
              </p>

              <div className="fd-calendar-block">
                <div className="fd-calendar-head">
                  <button
                    type="button"
                    className="fd-cal-nav"
                    onClick={() => shiftMonth(-1)}
                    aria-label="Previous month"
                  >
                    <span className="material-symbols-outlined">chevron_left</span>
                  </button>
                  <p>
                    {new Date(viewMonth.year, viewMonth.month).toLocaleDateString("en-US", {
                      month: "long",
                      year: "numeric",
                    })}
                  </p>
                  <button
                    type="button"
                    className="fd-cal-nav"
                    onClick={() => shiftMonth(1)}
                    aria-label="Next month"
                  >
                    <span className="material-symbols-outlined">chevron_right</span>
                  </button>
                </div>
                {slotsLoading ? (
                  <p className="fd-muted fd-cal-loading">Loading available dates...</p>
                ) : (
                  <>
                    <div className="fd-calendar-weekdays">
                      {WEEKDAYS.map((d, i) => (
                        <span key={`${d}-${i}`}>{d}</span>
                      ))}
                    </div>
                    <div className="fd-calendar-grid">
                      {calendarCells.map((cell) =>
                        cell.day === null ? (
                          <span key={cell.key} className="fd-cal-empty" aria-hidden />
                        ) : (
                          <button
                            key={cell.key}
                            type="button"
                            className={`fd-cal-day${cell.available ? " fd-cal-day--available" : ""}${selectedDate === cell.key ? " fd-cal-day--active" : ""}${cell.past ? " fd-cal-day--past" : ""}`}
                            disabled={!cell.available || cell.past}
                            onClick={() => selectDate(cell.key)}
                            title={cell.available ? dayLabel(cell.key) : undefined}
                          >
                            {cell.day}
                          </button>
                        )
                      )}
                    </div>
                    {availableDates.length > 0 && (
                      <p className="fd-cal-hint">
                        {availableDates.length} day{availableDates.length === 1 ? "" : "s"} with open slots
                      </p>
                    )}
                  </>
                )}
              </div>

              <div className="fd-slots-block">
                <p className="fd-slots-label">Available Slots</p>
                {slotsForDate.length === 0 ? (
                  <p className="fd-muted">No slots on this date. Pick another day.</p>
                ) : (
                  <div className="fd-slot-grid">
                    {slotsForDate.map((slot, i) => (
                      <button
                        key={i}
                        type="button"
                        className={`fd-slot-btn${selectedSlot === slot ? " fd-slot-btn--active" : ""}`}
                        onClick={() => setSelectedSlot(slot)}
                      >
                        {formatSlotTime(slot.slot_time)}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <button
                type="button"
                className="fd-confirm-btn"
                disabled={!selectedSlot || booking}
                onClick={() => void confirmBooking()}
              >
                {booking ? "Booking..." : "Confirm Appointment"}
                <span className="material-symbols-outlined">calendar_today</span>
              </button>
              <p className="fd-booking-note">No payment required until the visit.</p>
            </>
          ) : (
            <p className="fd-muted">Select a doctor to view available times.</p>
          )}
        </aside>
      </div>

      <section className="fd-trust-row">
        <div className="fd-trust-item">
          <span className="material-symbols-outlined">security</span>
          <div>
            <strong>HIPAA Compliant</strong>
            <p>Your medical data is encrypted and secure.</p>
          </div>
        </div>
        <div className="fd-trust-item">
          <span className="material-symbols-outlined">workspace_premium</span>
          <div>
            <strong>Board Certified</strong>
            <p>All specialists undergo rigorous verification.</p>
          </div>
        </div>
        <div className="fd-trust-item">
          <span className="material-symbols-outlined">support_agent</span>
          <div>
            <strong>24/7 Support</strong>
            <p>Need help? Our team is available anytime.</p>
          </div>
        </div>
      </section>
    </div>
  );
}
