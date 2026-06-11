import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { clearTokens } from "../api/client";
import PatientLayout from "./PatientLayout";
import DoctorLayout from "./doctor/DoctorLayout";

export default function Layout() {
  const loc = useLocation();
  const nav = useNavigate();
  const role = localStorage.getItem("user_role") || "patient";

  if (role === "patient") {
    return <PatientLayout />;
  }

  if (role === "doctor") {
    return <DoctorLayout />;
  }

  const links: Record<string, { to: string; label: string }[]> = {
    admin: [{ to: "/admin", label: "Admin Panel" }],
  };

  const logout = () => {
    clearTokens();
    nav("/login");
  };

  return (
    <div className="layout">
      <nav className="sidebar">
        <h2>🏥 MedAssist AI</h2>
        {localStorage.getItem("user_name") && (
          <p style={{ fontSize: "0.8rem", color: "#9ecae1", marginBottom: "1rem" }}>
            {localStorage.getItem("user_name")}
          </p>
        )}
        {links[role]?.map((l) => (
          <Link key={l.to} to={l.to} className={loc.pathname === l.to ? "active" : ""}>
            {l.label}
          </Link>
        ))}
        <button
          className="btn btn-outline"
          style={{ marginTop: "2rem", width: "100%", color: "#cde", borderColor: "#cde" }}
          onClick={logout}
        >
          Logout
        </button>
      </nav>
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}
