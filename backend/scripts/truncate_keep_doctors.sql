-- Wipe all data except the doctor directory (doctors, their user accounts,
-- specializations, doctor_specializations, doctor_availability).

BEGIN;

UPDATE doctor_availability SET status = 'available' WHERE status = 'booked';

DELETE FROM messages;
DELETE FROM symptom_assessments;
DELETE FROM conversation_memory;
DELETE FROM conversations;
DELETE FROM doctor_notes;
DELETE FROM patient_summaries;
DELETE FROM appointments;
DELETE FROM reports;
DELETE FROM allergies;
DELETE FROM medications;
DELETE FROM medical_history;
DELETE FROM patients;

DELETE FROM refresh_tokens;
DELETE FROM notifications;
DELETE FROM audit_logs;

DELETE FROM users WHERE role <> 'doctor';

COMMIT;
