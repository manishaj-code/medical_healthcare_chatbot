import { useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { clearTokens } from "../../api/client";
import NotificationDropdown from "../NotificationDropdown";
import "../../styles/doctor-portal.css";

export type DoctorTab = "overview" | "refills" | "patients" | "appointments" | "history" | "slots";

export interface DoctorOutletContext {
  search: string;
  activeTab: DoctorTab;
  setActiveTab: (tab: DoctorTab) => void;
}

const NAV: { tab?: DoctorTab; to?: string; label: string; icon: string; hash?: string }[] = [
  { tab: "overview", to: "/doctor", label: "Dashboards", icon: "dashboard" },
  { tab: "refills", label: "Refills", icon: "medication" },
  { tab: "patients", label: "Patients", icon: "group" },
  { tab: "appointments", label: "Appointments", icon: "event" },
  { tab: "history", label: "Consultation History", icon: "history" },
  { tab: "slots", label: "Availability", icon: "schedule" },
];

export default function DoctorLayout() {
  const loc = useLocation();
  const nav = useNavigate();
  const doctorName = localStorage.getItem("user_name") || "Doctor";
  const onPatientPage = loc.pathname.startsWith("/doctor/patients/");
  const [search, setSearch] = useState("");
  const [activeTab, setActiveTab] = useState<DoctorTab>("overview");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const logout = () => {
    clearTokens();
    nav("/login");
  };

  const goTab = (tab: DoctorTab, hash?: string) => {
    setActiveTab(tab);
    setSidebarOpen(false);
    if (loc.pathname !== "/doctor") {
      nav("/doctor");
      return;
    }
    if (hash) {
      requestAnimationFrame(() => {
        document.querySelector(hash)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    } else {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  const displayName = doctorName.startsWith("Dr.") ? doctorName : `Dr. ${doctorName}`;

  return (
    <div className="dp-shell">
      <aside className={`dp-sidebar${sidebarOpen ? " dp-sidebar--open" : ""}`}>
        <div className="dp-brand">
          <div className="dp-brand-icon">
            <span className="material-symbols-outlined filled-icon">medical_services</span>
          </div>
          <div>
            <h1 className="dp-brand-title">MediAI</h1>
            <p className="dp-brand-sub">Doctor Portal</p>
          </div>
        </div>

        <nav className="dp-nav">
          {NAV.map((item) => {
            const isActive =
              !onPatientPage &&
              loc.pathname === "/doctor" &&
              (item.tab ? activeTab === item.tab && !item.hash : false);

            if (item.hash) {
              return (
                <button
                  key={item.label}
                  type="button"
                  className="dp-nav-link"
                  onClick={() => {
                    setActiveTab("overview");
                    goTab("overview", item.hash);
                  }}
                >
                  <span className="material-symbols-outlined">{item.icon}</span>
                  <span>{item.label}</span>
                </button>
              );
            }

            if (item.to) {
              return (
                <Link
                  key={item.label}
                  to={item.to}
                  className={`dp-nav-link${isActive ? " dp-nav-link--active" : ""}`}
                  onClick={() => item.tab && setActiveTab(item.tab)}
                >
                  <span className="material-symbols-outlined filled-icon">{item.icon}</span>
                  <span>{item.label}</span>
                </Link>
              );
            }

            return (
              <button
                key={item.label}
                type="button"
                className={`dp-nav-link${isActive ? " dp-nav-link--active" : ""}`}
                onClick={() => item.tab && goTab(item.tab)}
              >
                <span className="material-symbols-outlined">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        <div className="dp-sidebar-foot">
          <button type="button" className="dp-btn dp-btn--primary dp-btn--block" onClick={() => goTab("slots")}>
            <span className="material-symbols-outlined">add</span>
            Manage Slots
          </button>
          <button type="button" className="dp-nav-link dp-nav-link--muted" onClick={logout}>
            <span className="material-symbols-outlined">logout</span>
            <span>Sign out</span>
          </button>
        </div>
      </aside>

      {sidebarOpen && (
        <button
          type="button"
          className="dp-sidebar-backdrop"
          aria-label="Close menu"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <main className="dp-main">
        <header className="dp-topbar">
          <div className="dp-topbar-left">
            <button
              type="button"
              className="dp-menu-toggle"
              aria-label="Open menu"
              onClick={() => setSidebarOpen(true)}
            >
              <span className="material-symbols-outlined">menu</span>
            </button>
            {!onPatientPage ? (
              <div className="dp-search-wrap">
                <span className="material-symbols-outlined">search</span>
                <input
                  type="search"
                  placeholder="Search patients by name…"
                  aria-label="Search patients"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    if (activeTab !== "patients") setActiveTab("patients");
                  }}
                />
              </div>
            ) : (
              <span style={{ fontWeight: 600, color: "var(--dp-on-surface-variant)", fontSize: "0.9rem" }}>
                Patient record
              </span>
            )}
          </div>
          <div className="dp-topbar-actions">
            <NotificationDropdown
              apiPrefix="/api/v1/doctor"
              viewAllPath="/doctor/notifications"
              variant="doctor"
            />
            <div className="dp-profile">
              <div className="dp-profile-text">
                <p className="dp-profile-name">{displayName}</p>
                <p className="dp-profile-role">Clinical Portal</p>
              </div>
              <div className="dp-profile-avatar">{doctorName.slice(0, 1).toUpperCase()}</div>
            </div>
          </div>
        </header>

        <div className="dp-content">
          <Outlet context={{ search, activeTab, setActiveTab } satisfies DoctorOutletContext} />
        </div>
      </main>
    </div>
  );
}
