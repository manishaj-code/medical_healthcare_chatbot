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
    cancellation = "cancellation"
    system = "system"
