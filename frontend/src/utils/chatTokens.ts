/**
 * Shared internal chat token constants and helpers.
 *
 * Both the MediAI guest widget (landing page) and the patient portal
 * AI Consultation chat use these tokens as API triggers.
 * The tokens are NEVER shown to the user — they are mapped to
 * friendly display labels before rendering.
 */

export const START_SYMPTOM_TRIAGE = "[start_symptom_triage]";
export const START_FIND_DOCTOR    = "[start_find_doctor]";
export const START_EXPLAIN_REPORT = "[start_explain_report]";
export const AURA_MAIN_MENU       = "[aura_main_menu]";
export const AURA_TYPE_SYMPTOMS   = "[aura_type_symptoms]";

/** All internal tokens that must never be shown as raw text in the UI */
export const INTERNAL_TOKEN_LABELS: Record<string, string> = {
  [START_SYMPTOM_TRIAGE]: "🩺 Check My Symptoms",
  [START_FIND_DOCTOR]:    "👨‍⚕️ Find a Specialist Doctor",
  [START_EXPLAIN_REPORT]: "📄 Explain My Medical Report",
  [AURA_MAIN_MENU]:       "🏠 Main Menu",
  [AURA_TYPE_SYMPTOMS]:   "📝 Type My Own Symptoms",
  "[aura_find_by_symptoms]": "By Symptoms",
  "[aura_find_by_specialty]": "By Specialty",
  "[aura_find_near_me]": "Near Me",
  "[aura_view_all_doctors]": "View All Doctors",
  "[aura_specialty_more]": "More…",
  "[aura_upload_report]": "📄 Upload Report",
  "[aura_upload_prescription]": "💊 Upload Prescription",
  "[aura_upload_lab]": "🧪 Upload Lab Report",
  "[aura_upload_image]": "🖼️ Upload Image",
  "[aura_upload_symptom_image]": "📷 Upload Symptom Photo",
};

/**
 * Quick-action buttons shown on the MediAI welcome screen.
 * label  = text shown on the button and in the user message bubble
 * token  = raw value sent to the API
 */
/** Welcome shortcuts — each maps to a working backend flow. */
export const CHAT_QUICK_ACTIONS = [
  { label: "Check symptoms", token: START_SYMPTOM_TRIAGE },
  { label: "Find a doctor", token: START_FIND_DOCTOR },
  { label: "Explain my report", token: START_EXPLAIN_REPORT },
] as const;

/**
 * Resolve a user-facing display string from message content.
 * If the content is a raw internal token, return its friendly label.
 * Otherwise return the content unchanged.
 */
export function resolveDisplayText(content: string): string {
  const trimmed = content.trim();
  return INTERNAL_TOKEN_LABELS[trimmed] ?? trimmed;
}
