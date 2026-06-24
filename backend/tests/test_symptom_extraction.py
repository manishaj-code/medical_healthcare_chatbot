"""Symptom extraction — filter booking/UI phrases from detected symptoms."""
from app.multi_agent.offline_fallback import conversational_triage_turn, is_symptom_triage_kickoff
from app.services.symptom_extraction import (
    extract_symptoms_offline,
    filter_symptom_labels,
    is_non_symptom_message,
    is_positive_wellness_update,
    is_vague_wellness_complaint,
    merge_symptom_lists,
)


def test_not_feeling_well_is_vague_complaint_not_symptom():
    assert is_vague_wellness_complaint("I am not feeling well")
    assert is_vague_wellness_complaint("I'm not feeling well")
    assert extract_symptoms_offline("I am not feeling well") == []
    assert is_symptom_triage_kickoff("I am not feeling well")


def test_feeling_good_is_not_symptom_or_triage_kickoff():
    assert is_positive_wellness_update("feeling good")
    assert is_non_symptom_message("feeling good")
    assert not is_vague_wellness_complaint("feeling good")
    assert extract_symptoms_offline("feeling good") == []
    assert not is_symptom_triage_kickoff("feeling good")


def test_not_feeling_well_triggers_symptom_kickoff_reply():
    session = {"_patient_first_name": "John"}
    triage = conversational_triage_turn("I am not feeling well", session)
    assert "what symptoms" in triage["reply"].lower()
    assert "well" not in triage["reply"].lower().split("dealing with")[-1] if "dealing with" in triage["reply"].lower() else True
    assert "dealing with" not in triage["reply"].lower()


def test_fever_still_extracted():
    assert extract_symptoms_offline("I have fever and headache") == ["Fever", "Headache"]


def test_book_appointment_is_not_a_symptom_message():
    assert is_non_symptom_message("Book appointment")
    assert is_non_symptom_message("book an appointment")


def test_book_appointment_not_extracted_offline():
    assert extract_symptoms_offline("Book appointment", ["Fever", "Headache"]) == ["Fever", "Headache"]


def test_filter_symptom_labels_removes_booking_actions():
    assert filter_symptom_labels(["Fever", "Headache", "Book Appointment"]) == ["Fever", "Headache"]


def test_merge_symptom_lists_skips_booking_actions():
    assert merge_symptom_lists(["Fever"], ["Book appointment", "Headache"]) == ["Fever", "Headache"]
