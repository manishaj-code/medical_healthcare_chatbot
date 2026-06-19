import { Skeleton, SkeletonPage } from "./Skeleton";

function AppointmentCardSkeleton() {
  return (
    <div className="sk-appt-card">
      <Skeleton circle width={48} height={48} />
      <div className="sk-appt-card-body">
        <Skeleton width="55%" height={16} />
        <Skeleton width="40%" height={14} />
        <Skeleton width="70%" height={14} />
      </div>
    </div>
  );
}

function DoctorCardSkeleton() {
  return (
    <div className="sk-doctor-card">
      <Skeleton circle width={56} height={56} />
      <div className="sk-appt-card-body">
        <Skeleton width="45%" height={18} />
        <Skeleton width="35%" height={14} />
        <Skeleton width="60%" height={14} />
        <Skeleton width="30%" height={32} rounded style={{ marginTop: 4 }} />
      </div>
    </div>
  );
}

export function AppointmentListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <SkeletonPage label="Loading appointments">
      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        {Array.from({ length: count }, (_, i) => (
          <AppointmentCardSkeleton key={i} />
        ))}
      </div>
    </SkeletonPage>
  );
}

export function PatientDashboardSkeleton() {
  return (
    <SkeletonPage label="Loading dashboard">
      <div className="sk-pd-welcome">
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 10 }}>
          <Skeleton width="40%" height={28} />
          <Skeleton width="85%" height={16} />
          <Skeleton width="70%" height={16} />
          <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
            <Skeleton width={120} height={28} rounded />
            <Skeleton width={140} height={28} rounded />
          </div>
        </div>
        <Skeleton width={200} height={44} rounded />
      </div>

      <div className="sk-pd-split">
        <div>
          <Skeleton width="50%" height={22} style={{ marginBottom: 12 }} />
          <AppointmentListSkeleton count={2} />
        </div>
        <div className="sk-insights-panel">
          <Skeleton width="60%" height={20} />
          <Skeleton width="100%" height={60} rounded />
          <Skeleton width="100%" height={60} rounded />
          <Skeleton width="45%" height={36} rounded />
        </div>
      </div>

      <Skeleton width="35%" height={22} style={{ marginBottom: 12 }} />
      <div className="sk-table-rows">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="sk-table-row">
            <div>
              <Skeleton width="70%" height={14} />
              <Skeleton width="50%" height={12} style={{ marginTop: 6 }} />
            </div>
            <Skeleton width="80%" height={14} />
            <Skeleton width="60%" height={14} />
            <Skeleton width={72} height={24} rounded />
            <Skeleton circle width={32} height={32} />
          </div>
        ))}
      </div>
    </SkeletonPage>
  );
}

export function DoctorGridSkeleton({ count = 4 }: { count?: number }) {
  return (
    <SkeletonPage label="Loading doctors">
      <Skeleton width="35%" height={22} style={{ marginBottom: 16 }} />
      {Array.from({ length: count }, (_, i) => (
        <DoctorCardSkeleton key={i} />
      ))}
    </SkeletonPage>
  );
}

export function CalendarSlotsSkeleton() {
  return (
    <SkeletonPage label="Loading available dates">
      <Skeleton width="50%" height={16} style={{ marginBottom: 12 }} />
      <div className="sk-cal-slots">
        {Array.from({ length: 7 }, (_, i) => (
          <Skeleton key={i} height={48} rounded />
        ))}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 16 }}>
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} width={72} height={36} rounded />
        ))}
      </div>
    </SkeletonPage>
  );
}

export function HealthRecordsSkeleton() {
  return (
    <SkeletonPage label="Loading health records">
      <div style={{ display: "flex", gap: 24, marginBottom: 24 }}>
        <Skeleton width={100} height={48} rounded />
        <Skeleton width={120} height={48} rounded />
      </div>
      <div className="sk-insights-panel" style={{ marginBottom: 20 }}>
        <Skeleton width="40%" height={20} />
        <Skeleton width="100%" height={80} rounded />
      </div>
      {Array.from({ length: 2 }, (_, i) => (
        <div key={i} className="sk-report-card">
          <Skeleton width="35%" height={20} />
          <Skeleton width="100%" height={14} />
          <Skeleton width="90%" height={14} />
          <Skeleton width="60%" height={14} />
        </div>
      ))}
    </SkeletonPage>
  );
}

export function ReportsListSkeleton({ count = 3 }: { count?: number }) {
  return (
    <SkeletonPage label="Loading reports">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="sk-report-card">
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <Skeleton width={40} height={40} rounded />
            <div style={{ flex: 1 }}>
              <Skeleton width="50%" height={16} />
              <Skeleton width="35%" height={12} style={{ marginTop: 6 }} />
            </div>
          </div>
          <Skeleton width="100%" height={14} />
          <Skeleton width="75%" height={14} />
        </div>
      ))}
    </SkeletonPage>
  );
}

export function NotificationsPageSkeleton() {
  return (
    <SkeletonPage label="Loading notifications">
      <div className="sk-notifications-grid">
        {Array.from({ length: 2 }, (_, panel) => (
          <div key={panel} className="sk-notifications-panel">
            <Skeleton width="55%" height={18} />
            {Array.from({ length: 3 }, (_, i) => (
              <div key={i} className="sk-appt-card">
                <Skeleton width={36} height={36} rounded />
                <div className="sk-appt-card-body">
                  <Skeleton width="65%" height={14} />
                  <Skeleton width="45%" height={12} />
                </div>
              </div>
            ))}
          </div>
        ))}
      </div>
    </SkeletonPage>
  );
}

export function ChatPageSkeleton() {
  return (
    <SkeletonPage label="Loading consultation">
      <div className="sk-chat-messages">
        <div className="sk-chat-msg">
          <Skeleton circle width={40} height={40} />
          <Skeleton width="65%" height={72} rounded />
        </div>
        <div className="sk-chat-msg sk-chat-msg--right">
          <Skeleton circle width={40} height={40} />
          <Skeleton width="45%" height={48} rounded />
        </div>
        <div className="sk-chat-msg">
          <Skeleton circle width={40} height={40} />
          <Skeleton width="70%" height={96} rounded />
        </div>
      </div>
    </SkeletonPage>
  );
}

export function VideoConsultSkeleton() {
  return (
    <SkeletonPage label="Loading video room">
      <Skeleton width={180} height={36} rounded style={{ marginBottom: 16 }} />
      <Skeleton width="35%" height={28} style={{ marginBottom: 8 }} />
      <Skeleton width="25%" height={14} style={{ marginBottom: 20 }} />
      <Skeleton className="sk-video-frame" height={420} rounded />
    </SkeletonPage>
  );
}

export function VideoModalSkeleton() {
  return (
    <SkeletonPage label="Preparing video room">
      <Skeleton width="100%" height={360} rounded />
      <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
        <Skeleton width={120} height={36} rounded />
        <Skeleton width={100} height={36} rounded />
      </div>
    </SkeletonPage>
  );
}

export function PrepTabSkeleton() {
  return (
    <SkeletonPage label="Loading content">
      <Skeleton width="40%" height={18} style={{ marginBottom: 12 }} />
      <Skeleton width="100%" height={14} />
      <Skeleton width="92%" height={14} style={{ marginTop: 8 }} />
      <Skeleton width="88%" height={14} style={{ marginTop: 8 }} />
      <Skeleton width="75%" height={14} style={{ marginTop: 8 }} />
    </SkeletonPage>
  );
}

export function ReportModalSkeleton() {
  return (
    <SkeletonPage label="Loading report">
      <Skeleton width="50%" height={20} style={{ marginBottom: 16 }} />
      <Skeleton width="100%" height={14} />
      <Skeleton width="95%" height={14} style={{ marginTop: 8 }} />
      <Skeleton width="80%" height={14} style={{ marginTop: 8 }} />
    </SkeletonPage>
  );
}

export function DropdownNotificationsSkeleton({ count = 3 }: { count?: number }) {
  return (
    <SkeletonPage label="Loading notifications">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} style={{ display: "flex", gap: 10, alignItems: "center", padding: "8px 0" }}>
          <Skeleton width={28} height={28} rounded />
          <div style={{ flex: 1 }}>
            <Skeleton width="70%" height={12} />
            <Skeleton width="50%" height={10} style={{ marginTop: 6 }} />
          </div>
        </div>
      ))}
    </SkeletonPage>
  );
}

export function PatientDetailSkeleton() {
  return (
    <SkeletonPage label="Loading patient record">
      <div className="sk-dp-patient-header">
        <Skeleton circle width={72} height={72} />
        <div style={{ flex: 1 }}>
          <Skeleton width="30%" height={24} />
          <Skeleton width="50%" height={14} style={{ marginTop: 8 }} />
          <Skeleton width="40%" height={14} style={{ marginTop: 6 }} />
        </div>
        <Skeleton width={160} height={40} rounded />
      </div>
      <div className="sk-dp-tabs">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} width={100} height={36} rounded />
        ))}
      </div>
      <div className="sk-dp-panel">
        <Skeleton width="40%" height={20} />
        <Skeleton width="100%" height={14} />
        <Skeleton width="95%" height={14} />
        <Skeleton width="80%" height={14} />
        <Skeleton width="100%" height={120} rounded style={{ marginTop: 8 }} />
      </div>
    </SkeletonPage>
  );
}

export function ConsultationSessionSkeleton() {
  return (
    <SkeletonPage label="Loading consultation">
      <Skeleton width="45%" height={24} style={{ marginBottom: 16 }} />
      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} width={120} height={8} rounded />
        ))}
      </div>
      <div className="sk-dp-consult">
        <div className="sk-dp-panel">
          <Skeleton width="50%" height={20} />
          <Skeleton width="100%" height={14} />
          <Skeleton width="90%" height={14} />
          <Skeleton width="100%" height={160} rounded />
        </div>
        <div className="sk-dp-panel">
          <Skeleton width="45%" height={20} />
          <Skeleton width="100%" height={100} rounded />
          <Skeleton width="100%" height={100} rounded />
          <Skeleton width="100%" height={48} rounded />
        </div>
      </div>
    </SkeletonPage>
  );
}

export function ConsultationHistorySkeleton({ count = 4 }: { count?: number }) {
  return (
    <SkeletonPage label="Loading consultation history">
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} width={88} height={32} rounded />
        ))}
      </div>
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="sk-dp-history-card">
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <Skeleton width="25%" height={18} />
            <Skeleton width={80} height={24} rounded />
          </div>
          <Skeleton width="60%" height={14} />
          <Skeleton width="90%" height={14} />
        </div>
      ))}
    </SkeletonPage>
  );
}

export function RefillTableSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <SkeletonPage label="Loading refill requests">
      <div className="sk-admin-table">
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="sk-admin-row" style={{ gridTemplateColumns: "1fr 1.2fr 0.8fr 0.6fr" }}>
            <Skeleton height={14} />
            <Skeleton height={14} />
            <Skeleton height={14} />
            <Skeleton width={80} height={32} rounded />
          </div>
        ))}
      </div>
    </SkeletonPage>
  );
}

export function DoctorNotificationsSkeleton() {
  return (
    <SkeletonPage label="Loading notifications">
      {Array.from({ length: 5 }, (_, i) => (
        <div key={i} className="sk-dp-history-card">
          <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
            <Skeleton width={32} height={32} rounded />
            <div style={{ flex: 1 }}>
              <Skeleton width="30%" height={14} />
              <Skeleton width="85%" height={14} style={{ marginTop: 6 }} />
            </div>
            <Skeleton width={100} height={12} />
          </div>
        </div>
      ))}
    </SkeletonPage>
  );
}

export function AdminPanelSkeleton() {
  return (
    <SkeletonPage label="Loading admin data">
      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} width={120} height={40} rounded />
        ))}
      </div>
      <Skeleton width="30%" height={22} style={{ marginBottom: 8 }} />
      <Skeleton width="60%" height={14} style={{ marginBottom: 16 }} />
      <div className="sk-admin-table">
        <div className="sk-admin-row">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} height={12} />
          ))}
        </div>
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="sk-admin-row">
            {Array.from({ length: 6 }, (_, j) => (
              <Skeleton key={j} height={14} />
            ))}
          </div>
        ))}
      </div>
    </SkeletonPage>
  );
}

export function UrgentPanelSkeleton() {
  return (
    <SkeletonPage label="Loading urgent consultations">
      <div className="sk-dp-urgent">
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <Skeleton width="40%" height={22} />
          <Skeleton width={100} height={32} rounded />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} height={64} rounded />
          ))}
        </div>
        {Array.from({ length: 2 }, (_, i) => (
          <Skeleton key={i} height={88} rounded />
        ))}
      </div>
    </SkeletonPage>
  );
}
