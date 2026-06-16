import enum


class UserRole(str, enum.Enum):
    patient = "patient"
    doctor = "doctor"
    admin = "admin"


class AppointmentStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    cancelled = "cancelled"
    completed = "completed"
    rescheduled = "rescheduled"


class RiskLevel(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    emergency = "emergency"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"


class NotificationType(str, enum.Enum):
    booking_confirmation = "booking_confirmation"
    reminder = "reminder"
    reminder_scheduled = "reminder_scheduled"
    cancellation = "cancellation"
    system = "system"
    refill_request = "refill_request"
    refill_approved = "refill_approved"
    refill_denied = "refill_denied"
    video_consultation = "video_consultation"
    urgent_consult_request = "urgent_consult_request"
    urgent_consult_assigned = "urgent_consult_assigned"
    urgent_consult_superseded = "urgent_consult_superseded"
    urgent_consult_declined = "urgent_consult_declined"
    urgent_consult_expanded = "urgent_consult_expanded"
    urgent_consult_unavailable = "urgent_consult_unavailable"


class UrgentConsultRequestStatus(str, enum.Enum):
    pending = "pending"
    assigned = "assigned"
    expired = "expired"
    cancelled = "cancelled"


class UrgentConsultOfferStatus(str, enum.Enum):
    notified = "notified"
    accepted = "accepted"
    declined = "declined"
    superseded = "superseded"
    expired = "expired"


class RefillRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
