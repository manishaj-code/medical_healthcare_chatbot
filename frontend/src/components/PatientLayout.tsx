import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { clearTokens } from "../api/client";
import NotificationDropdown from "./NotificationDropdown";

function userInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return (parts[0]?.[0] ?? "P").toUpperCase();
}

const NAV = [
  { to: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { to: "/chat", label: "AI Consultation", icon: "smart_toy" },
  { to: "/doctors", label: "Find Doctors", icon: "medical_services" },
  { to: "/appointments", label: "Appointments", icon: "event" },
  { to: "/reports", label: "My Reports", icon: "description" },
  { to: "/health-records", label: "Health Records", icon: "medical_information" },
  { to: "/notifications", label: "Notifications", icon: "notifications" },
];

const PAGE_TITLES: Record<string, string> = {
  "/dashboard": "Dashboard",
  "/doctors": "Find Doctors",
  "/appointments": "Appointments",
  "/reports": "My Reports",
  "/health-records": "Health Records",
  "/notifications": "Notifications",
};

function pageTitle(pathname: string): string {
  const match = Object.entries(PAGE_TITLES).find(([path]) => pathname.startsWith(path));
  return match?.[1] ?? "Patient Portal";
}

export default function PatientLayout() {
  const loc = useLocation();
  const nav = useNavigate();
  const name = localStorage.getItem("user_name") || "Patient";
  const isChat = loc.pathname.startsWith("/chat");

  const logout = () => {
    clearTokens();
    nav("/login");
  };

  const isActive = (path: string) => {
    if (path === "/dashboard") return loc.pathname === "/dashboard";
    return loc.pathname.startsWith(path);
  };

  return (
    <div className="patient-shell">
      <aside className="patient-sidebar">
        <div className="patient-brand">
          <h1>MediAI Platform</h1>
          <p>Precision Care AI</p>
        </div>

        <nav className="patient-nav">
          {NAV.map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className={`patient-nav-link ${isActive(item.to) ? "active" : ""}`}
            >
              <span className="material-symbols-outlined">{item.icon}</span>
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>

        <div className="patient-sidebar-footer">
          <Link to="/doctors" className="patient-new-appt-btn">
            <span className="material-symbols-outlined">add</span>
            New Appointment
          </Link>
          <div className="patient-user-card">
            <div className="patient-avatar">{userInitials(name)}</div>
            <div>
              <p className="patient-user-name">{name}</p>
              <p className="patient-user-meta">Patient Portal</p>
            </div>
          </div>
          <button type="button" className="patient-logout-btn" onClick={logout}>
            Logout
          </button>
        </div>
      </aside>

      <div className={`patient-main-wrap${isChat ? " patient-main-wrap--chat" : ""}`}>
        {!isChat && (
          <header className="patient-topbar">
            <h2 className="patient-topbar-title">{pageTitle(loc.pathname)}</h2>
            <div className="patient-topbar-actions">
              <NotificationDropdown
                apiPrefix="/api/v1/patients/me"
                viewAllPath="/notifications"
              />
              <div className="patient-topbar-user" aria-label={`Signed in as ${name}`}>
                <span className="patient-topbar-user-name">{name}</span>
                <div className="patient-topbar-avatar">{userInitials(name)}</div>
              </div>
            </div>
          </header>
        )}

        <main className={`patient-main${isChat ? " patient-main--chat" : ""}`}>
          <Outlet />
        </main>
      </div>

      {!isChat && (
        <Link to="/chat" className="patient-fab" title="Start AI Consultation">
          <span className="material-symbols-outlined">smart_toy</span>
        </Link>
      )}
    </div>
  );
}
