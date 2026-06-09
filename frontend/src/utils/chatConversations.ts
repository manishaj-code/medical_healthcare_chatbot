import { api } from "../api/client";

export interface Conversation {
  id: string;
  title: string | null;
  created_at: string;
  emergency_flag?: boolean;
}

export const CHAT_LIST_TITLE = "Health Chat";

let ensureTodayInFlight: Promise<Conversation> | null = null;

export function defaultChatTitle(): string {
  return CHAT_LIST_TITLE;
}

export function formatChatDateLabel(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      day: "numeric",
      month: "short",
      year: "numeric",
    });
  } catch {
    return "";
  }
}

export function dateKey(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function getLocalDateKey(d = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function getTzOffsetMinutes(): number {
  return -new Date().getTimezoneOffset();
}

export function dedupeConversationsByDate(conversations: Conversation[]): Conversation[] {
  const seen = new Set<string>();
  return conversations.filter((c) => {
    const key = dateKey(c.created_at);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export async function fetchConversations(): Promise<Conversation[]> {
  const tz = getTzOffsetMinutes();
  const list = await api<Conversation[]>(`/api/v1/chat/conversations?tz_offset_minutes=${tz}`);
  return dedupeConversationsByDate(list);
}

export async function ensureTodayConversation(): Promise<Conversation> {
  if (!ensureTodayInFlight) {
    ensureTodayInFlight = api<Conversation>("/api/v1/chat/conversations/today", {
      method: "POST",
      body: JSON.stringify({
        local_date: getLocalDateKey(),
        tz_offset_minutes: getTzOffsetMinutes(),
        title: CHAT_LIST_TITLE,
      }),
    }).finally(() => {
      ensureTodayInFlight = null;
    });
  }
  return ensureTodayInFlight;
}
