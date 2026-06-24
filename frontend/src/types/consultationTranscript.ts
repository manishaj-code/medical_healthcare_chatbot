export interface TranscriptSegment {
  id: string;
  speaker_role: string;
  speaker_label: string | null;
  text: string;
  confidence: number | null;
  created_at: string;
}

export interface TranscriptSession {
  id: string;
  consultation_id: string;
  appointment_id: string;
  room_id: string | null;
  status: string;
  full_transcript_text: string | null;
  last_insights: StoredTranscriptInsights | null;
  started_at: string;
  ended_at: string | null;
}

export interface TranscriptSttConfig {
  provider: "deepgram";
  chunk_bytes: number;
  available: boolean;
  model?: string;
  error?: string;
}

export interface TranscriptStartResponse {
  session: TranscriptSession;
  resumed?: boolean;
  stt: TranscriptSttConfig;
}

export interface TranscriptSnapshot {
  session: TranscriptSession | null;
  segments: TranscriptSegment[];
}

export interface TranscriptAiSuggestions {
  batch_id: string;
  patient_concerns?: string[];
  transcript_summary?: string | null;
  chief_complaint_suggestion?: string | null;
  differential_considerations: string[];
  suggested_investigations: string[];
  matched_catalog_tests?: { test_code: string; test_name: string }[];
  suggested_follow_up_days: number | null;
  clinical_notes_draft: string | null;
  suggested_medications: {
    medicine_name: string;
    strength?: string;
    frequency?: string;
    duration?: string;
    rationale?: string;
  }[];
  allergy_warnings: string[];
  disclaimer: string;
}

export interface StoredTranscriptInsights {
  batch_id?: string;
  analyzed_at?: string;
  segment_count?: number;
  patient_concerns?: string[];
  transcript_summary?: string | null;
  chief_complaint_suggestion?: string | null;
  differential_considerations?: string[];
  suggested_investigations?: string[];
  matched_catalog_tests?: { test_code: string; test_name: string }[];
  suggested_follow_up_days?: number | null;
  clinical_notes_draft?: string | null;
  suggested_medications?: TranscriptAiSuggestions["suggested_medications"];
  allergy_warnings?: string[];
  disclaimer?: string;
}
