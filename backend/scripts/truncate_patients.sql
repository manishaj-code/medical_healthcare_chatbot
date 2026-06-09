-- Remove all patient accounts and related clinical/chat data.
-- Keeps doctors, admin, specializations, and doctor availability (booked slots reset).

BEGIN;

UPDATE doctor_availability SET status = 'available' WHERE status = 'booked';

DELETE FROM messages
WHERE conversation_id IN (SELECT id FROM conversations);

DELETE FROM symptom_assessments;
DELETE FROM conversation_memory;
DELETE FROM conversations;
DELETE FROM doctor_notes WHERE patient_id IS NOT NULL;
DELETE FROM patient_summaries;
DELETE FROM appointments;
DELETE FROM reports;
DELETE FROM allergies;
DELETE FROM medications;
DELETE FROM medical_history;

DELETE FROM refresh_tokens
WHERE user_id IN (SELECT id FROM users WHERE role = 'patient');

DELETE FROM notifications
WHERE user_id IN (SELECT id FROM users WHERE role = 'patient');

DELETE FROM audit_logs
WHERE actor_id IN (SELECT id FROM users WHERE role = 'patient');

DELETE FROM patients;

DELETE FROM users WHERE role = 'patient';

COMMIT;
