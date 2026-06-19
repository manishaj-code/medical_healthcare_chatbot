import type { StoredTranscriptInsights, TranscriptAiSuggestions } from "../types/consultationTranscript";

export type { StoredTranscriptInsights };

export function insightsToSuggestions(
  insights: StoredTranscriptInsights | null | undefined,
): TranscriptAiSuggestions | null {
  if (!insights?.batch_id) return null;
  return {
    batch_id: insights.batch_id,
    patient_concerns: insights.patient_concerns,
    transcript_summary: insights.transcript_summary ?? null,
    chief_complaint_suggestion: insights.chief_complaint_suggestion ?? null,
    differential_considerations: insights.differential_considerations ?? [],
    suggested_investigations: insights.suggested_investigations ?? [],
    matched_catalog_tests: insights.matched_catalog_tests,
    suggested_follow_up_days: insights.suggested_follow_up_days ?? null,
    clinical_notes_draft: insights.clinical_notes_draft ?? null,
    suggested_medications: insights.suggested_medications ?? [],
    allergy_warnings: insights.allergy_warnings ?? [],
    disclaimer:
      insights.disclaimer ??
      "AI-generated from live transcript — verify before clinical use.",
  };
}
