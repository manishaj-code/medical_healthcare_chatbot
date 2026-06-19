import { useCallback, useRef, useState } from "react";
import { api } from "../api/client";
import type { VideoConsultationSession, VideoParticipantRole } from "../types/videoConsultation";

function videoEndpoint(appointmentId: string, role: VideoParticipantRole): string {
  if (role === "doctor") {
    return `/api/v1/doctor/appointments/${appointmentId}/video`;
  }
  return `/api/v1/appointments/${appointmentId}/video`;
}

export function useVideoConsultation(role: VideoParticipantRole = "patient") {
  const [session, setSession] = useState<VideoConsultationSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const sessionRef = useRef<VideoConsultationSession | null>(null);
  const joinInFlightRef = useRef<string | null>(null);

  sessionRef.current = session;

  const joinAppointment = useCallback(
    async (appointmentId: string) => {
      const current = sessionRef.current;
      if (current?.appointment_id === appointmentId && current.token?.trim() && current.url?.trim()) {
        return current;
      }

      if (joinInFlightRef.current === appointmentId) {
        return current;
      }

      joinInFlightRef.current = appointmentId;
      if (!current || current.appointment_id !== appointmentId) {
        setSession(null);
      }
      setLoading(true);
      setError("");
      try {
        const data = await api<VideoConsultationSession>(videoEndpoint(appointmentId, role), {
          method: "POST",
        });
        setSession(data);
        sessionRef.current = data;
        if (!data.token?.trim() || !data.url?.trim()) {
          throw new Error(
            "Video service returned an invalid session. Check LiveKit configuration on the API.",
          );
        }
        return data;
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Could not start video call.";
        setError(message);
        throw err;
      } finally {
        if (joinInFlightRef.current === appointmentId) {
          joinInFlightRef.current = null;
        }
        setLoading(false);
      }
    },
    [role],
  );

  const reset = useCallback(() => {
    joinInFlightRef.current = null;
    sessionRef.current = null;
    setSession(null);
    setError("");
    setLoading(false);
  }, []);

  return { session, loading, error, joinAppointment, reset, role };
}
