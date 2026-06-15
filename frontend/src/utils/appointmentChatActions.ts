/** Chat messages for appointment management — keep in sync with ChatBookingUI buttons. */

export function appointmentDisplayId(appointment: { apt_id?: string; id: string }): string {
  return appointment.apt_id?.trim() || appointment.id;
}

export function buildRescheduleAppointmentMessage(aptId: string): string {
  return `I want to reschedule my appointment ${aptId}`;
}

export function buildCancelAppointmentMessage(aptId: string): string {
  return `Please cancel my appointment ${aptId}`;
}

export interface ChatNavigationState {
  conversationId?: string;
  fromGuestBooking?: boolean;
  pendingMessage?: string;
}
