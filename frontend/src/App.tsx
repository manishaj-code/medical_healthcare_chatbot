import { Navigate, Route, Routes } from "react-router-dom";
import Login from "./pages/Login";
import Landing from "./pages/Landing";
import PatientDashboard from "./pages/patient/Dashboard";
import PatientChat from "./pages/patient/Chat";
import PatientDoctors from "./pages/patient/Doctors";
import PatientAppointments from "./pages/patient/Appointments";
import PatientReports from "./pages/patient/Reports";
import PatientNotifications from "./pages/patient/Notifications";
import VideoConsultation from "./pages/patient/VideoConsultation";
import DoctorDashboard from "./pages/doctor/Dashboard";
import DoctorPatientDetail from "./pages/doctor/PatientDetail";
import DoctorNotifications from "./pages/doctor/Notifications";
import AdminPanel from "./pages/admin/Panel";
import Layout from "./components/Layout";

function homePathForRole(role: string | null): string {
  if (role === "doctor") return "/doctor";
  if (role === "admin") return "/admin";
  return "/dashboard";
}

function Protected({ children, roles }: { children: React.ReactNode; roles?: string[] }) {
  const token = localStorage.getItem("access_token");
  const role = localStorage.getItem("user_role");
  if (!token) return <Navigate to="/login" />;
  if (roles && role && !roles.includes(role)) return <Navigate to="/login" />;
  return <>{children}</>;
}

function HomeRoute() {
  const token = localStorage.getItem("access_token");
  if (token) {
    return <Navigate to={homePathForRole(localStorage.getItem("user_role"))} replace />;
  }
  return <Landing />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomeRoute />} />
      <Route path="/login" element={<Login />} />
      <Route element={<Layout />}>
        <Route path="/dashboard" element={<Protected roles={["patient"]}><PatientDashboard /></Protected>} />
        <Route path="/chat" element={<Protected roles={["patient"]}><PatientChat /></Protected>} />
        <Route path="/doctors" element={<Protected roles={["patient"]}><PatientDoctors /></Protected>} />
        <Route path="/appointments" element={<Protected roles={["patient"]}><PatientAppointments /></Protected>} />
        <Route path="/video/:appointmentId" element={<Protected roles={["patient"]}><VideoConsultation /></Protected>} />
        <Route path="/reports" element={<Protected roles={["patient"]}><PatientReports /></Protected>} />
        <Route path="/notifications" element={<Protected roles={["patient"]}><PatientNotifications /></Protected>} />
        <Route path="/doctor" element={<Protected roles={["doctor"]}><DoctorDashboard /></Protected>} />
        <Route path="/doctor/notifications" element={<Protected roles={["doctor"]}><DoctorNotifications /></Protected>} />
        <Route path="/doctor/patients/:patientId" element={<Protected roles={["doctor"]}><DoctorPatientDetail /></Protected>} />
        <Route path="/admin" element={<Protected roles={["admin"]}><AdminPanel /></Protected>} />
      </Route>
    </Routes>
  );
}
