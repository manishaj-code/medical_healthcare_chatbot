"""Symptom extraction — filter booking/UI phrases from detected symptoms."""
from app.services.symptom_extraction import (
    extract_symptoms_offline,
    filter_symptom_labels,
    is_non_symptom_message,
    merge_symptom_lists,
)


def test_book_appointment_is_not_a_symptom_message():
    assert is_non_symptom_message("Book appointment")
    assert is_non_symptom_message("book an appointment")


def test_book_appointment_not_extracted_offline():
    assert extract_symptoms_offline("Book appointment", ["Fever", "Headache"]) == ["Fever", "Headache"]


def test_filter_symptom_labels_removes_booking_actions():
    assert filter_symptom_labels(["Fever", "Headache", "Book Appointment"]) == ["Fever", "Headache"]


def test_merge_symptom_lists_skips_booking_actions():
    assert merge_symptom_lists(["Fever"], ["Book appointment", "Headache"]) == ["Fever", "Headache"]
