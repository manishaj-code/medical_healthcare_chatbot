"""Tests for RAG patient chart indexing."""
from app.rag.clinical_kb import load_clinical_kb_documents
from app.rag.embeddings import HashEmbeddingProvider
from app.rag.indexer import build_patient_chart_documents


def test_load_clinical_kb_seed():
    docs = load_clinical_kb_documents()
    assert len(docs) >= 10
    topics = {d.metadata.get("topic") for d in docs}
    assert "fever" in topics
    assert "medication" in topics or "diabetes" in topics


def test_build_patient_chart_documents_includes_allergies():
    ctx = {
        "patient_id": "p1",
        "allergies": ["Penicillin"],
        "medications": [{"name": "Metformin", "dosage": "500mg", "frequency": "daily"}],
        "conditions": ["Type 2 diabetes"],
        "recent_visits": [{"apt_id": "APT-1", "doctor_name": "Dr. Lee", "date": "2026-01-01", "time": "10:00 AM"}],
        "memory_facts": ["Reports occasional headaches"],
        "blood_group": "O+",
    }
    docs = build_patient_chart_documents(ctx)
    categories = {d.metadata.get("category") for d in docs}
    assert "allergy" in categories
    assert "medication" in categories
    assert "condition" in categories
    assert "visit" in categories
    allergy = next(d for d in docs if d.metadata.get("category") == "allergy")
    assert "Penicillin" in allergy.content
    assert allergy.metadata.get("high_priority") is True


async def test_hash_embedding_dimensions():
    provider = HashEmbeddingProvider(768)
    vec = await provider.embed_text("headache fever")
    assert len(vec) == 768
    assert abs(sum(x * x for x in vec) - 1.0) < 0.01
