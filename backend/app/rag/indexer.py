"""Build and upsert RAG index documents."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Patient
from app.models.rag_chunk import RagChunk
from app.rag.embeddings import get_embedding_provider
from app.rag.schemas import IndexType
from app.services.patient_context import load_patient_context


@dataclass
class IndexDocument:
    source_id: str
    title: str
    content: str
    metadata: dict


def build_patient_chart_documents(patient_ctx: dict) -> list[IndexDocument]:
    """Turn patient context dict into searchable chunks."""
    patient_id = patient_ctx.get("patient_id") or "unknown"
    docs: list[IndexDocument] = []

    for allergen in patient_ctx.get("allergies") or []:
        name = str(allergen).strip()
        if not name:
            continue
        docs.append(
            IndexDocument(
                source_id=f"{patient_id}:allergy:{name.lower()}",
                title=f"Allergy: {name}",
                content=f"Patient has a documented allergy to {name}. Avoid recommending {name} or related substances.",
                metadata={"category": "allergy", "high_priority": True, "allergen": name},
            )
        )

    for med in patient_ctx.get("medications") or []:
        if not isinstance(med, dict):
            continue
        name = str(med.get("name") or "").strip()
        if not name:
            continue
        dosage = str(med.get("dosage") or "").strip()
        frequency = str(med.get("frequency") or "").strip()
        parts = [f"Patient takes {name}"]
        if dosage:
            parts.append(f"dosage {dosage}")
        if frequency:
            parts.append(f"frequency {frequency}")
        docs.append(
            IndexDocument(
                source_id=f"{patient_id}:med:{name.lower()}",
                title=f"Medication: {name}",
                content=". ".join(parts) + ".",
                metadata={"category": "medication", "medication": name},
            )
        )

    for condition in patient_ctx.get("conditions") or []:
        name = str(condition).strip()
        if not name:
            continue
        docs.append(
            IndexDocument(
                source_id=f"{patient_id}:condition:{name.lower()}",
                title=f"Condition: {name}",
                content=f"Patient has medical history of {name}.",
                metadata={"category": "condition", "condition": name},
            )
        )

    for visit in patient_ctx.get("recent_visits") or []:
        if not isinstance(visit, dict):
            continue
        apt_id = str(visit.get("apt_id") or visit.get("id") or "visit")
        doctor = visit.get("doctor_name") or "doctor"
        date = visit.get("date") or ""
        time = visit.get("time") or ""
        docs.append(
            IndexDocument(
                source_id=f"{patient_id}:visit:{apt_id}",
                title=f"Recent visit: {date}",
                content=f"Recent visit with {doctor} on {date} at {time} (status: {visit.get('status', 'completed')}).",
                metadata={"category": "visit", "appointment_id": apt_id},
            )
        )

    for i, fact in enumerate(patient_ctx.get("memory_facts") or []):
        text = str(fact).strip()
        if not text:
            continue
        docs.append(
            IndexDocument(
                source_id=f"{patient_id}:memory:{i}",
                title="Patient note",
                content=text,
                metadata={"category": "memory"},
            )
        )

    bg = str(patient_ctx.get("blood_group") or "").strip()
    if bg:
        docs.append(
            IndexDocument(
                source_id=f"{patient_id}:blood_group",
                title="Blood group",
                content=f"Patient blood group: {bg}.",
                metadata={"category": "profile"},
            )
        )

    return docs


async def upsert_patient_index(db: AsyncSession, patient_id: UUID) -> int:
    """Rebuild patient chart vectors for one patient."""
    patient = await db.get(Patient, patient_id)
    if not patient:
        return 0

    patient_ctx = await load_patient_context(db, patient)
    documents = build_patient_chart_documents(patient_ctx)
    if not documents:
        await db.execute(
            delete(RagChunk).where(
                RagChunk.index_type == IndexType.PATIENT_CHART.value,
                RagChunk.patient_id == patient_id,
            )
        )
        return 0

    provider = get_embedding_provider()
    embeddings = await provider.embed_batch([d.content for d in documents])

    await db.execute(
        delete(RagChunk).where(
            RagChunk.index_type == IndexType.PATIENT_CHART.value,
            RagChunk.patient_id == patient_id,
        )
    )

    for doc, embedding in zip(documents, embeddings, strict=True):
        db.add(
            RagChunk(
                index_type=IndexType.PATIENT_CHART.value,
                patient_id=patient_id,
                source_id=doc.source_id,
                title=doc.title,
                content=doc.content,
                chunk_metadata=doc.metadata,
                embedding=embedding,
            )
        )

    await db.flush()
    return len(documents)
