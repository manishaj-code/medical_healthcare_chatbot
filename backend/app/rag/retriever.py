"""Semantic retrieval over rag_chunks."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_settings
from app.models.rag_chunk import RagChunk
from app.rag.embeddings import get_embedding_provider
from app.rag.clinical_kb import upsert_clinical_kb_index
from app.rag.indexer import upsert_patient_index
from app.rag.schemas import IndexType, RetrievedChunk


async def ensure_clinical_kb_index(db: AsyncSession) -> int:
    """Index clinical KB seed corpus if not yet loaded."""
    existing = await db.execute(
        select(RagChunk.id)
        .where(RagChunk.index_type == IndexType.CLINICAL_KB.value)
        .limit(1)
    )
    if existing.scalar_one_or_none():
        return 0
    return await upsert_clinical_kb_index(db)


async def ensure_patient_index(db: AsyncSession, patient_id: UUID) -> int:
    """Index patient chart if no chunks exist yet."""
    existing = await db.execute(
        select(RagChunk.id)
        .where(
            RagChunk.index_type == IndexType.PATIENT_CHART.value,
            RagChunk.patient_id == patient_id,
        )
        .limit(1)
    )
    if existing.scalar_one_or_none():
        return 0
    return await upsert_patient_index(db, patient_id)


async def retrieve_evidence(
    db: AsyncSession,
    *,
    query: str,
    indexes: list[IndexType | str],
    patient_id: UUID | None = None,
    top_k: int | None = None,
) -> list[RetrievedChunk]:
    """Cosine-similarity search with index and patient filters."""
    settings = get_settings()
    if not settings.rag_enabled or not query.strip():
        return []

    index_values = [
        idx.value if isinstance(idx, IndexType) else str(idx) for idx in indexes
    ]
    if not index_values:
        return []

    if patient_id and IndexType.PATIENT_CHART.value in index_values:
        await ensure_patient_index(db, patient_id)

    if IndexType.CLINICAL_KB.value in index_values:
        await ensure_clinical_kb_index(db)

    provider = get_embedding_provider()
    query_vec = await provider.embed_text(query.strip(), query=True)
    limit = top_k or settings.rag_top_k

    distance = RagChunk.embedding.cosine_distance(query_vec)
    stmt = (
        select(RagChunk, distance.label("distance"))
        .where(RagChunk.index_type.in_(index_values))
        .order_by(distance)
        .limit(limit)
    )
    if patient_id is not None:
        stmt = stmt.where(
            (RagChunk.patient_id == patient_id) | (RagChunk.patient_id.is_(None))
        )

    rows = (await db.execute(stmt)).all()
    chunks: list[RetrievedChunk] = []
    for row, dist in rows:
        score = max(0.0, 1.0 - float(dist))
        chunks.append(
            RetrievedChunk(
                id=str(row.id),
                index_type=row.index_type,
                source_id=row.source_id,
                title=row.title,
                content=row.content,
                score=round(score, 4),
                metadata=dict(row.chunk_metadata or {}),
            )
        )

    allergy_chunks = [c for c in chunks if c.metadata.get("category") == "allergy"]
    other = [c for c in chunks if c.metadata.get("category") != "allergy"]
    return allergy_chunks + other


def format_chunks_for_prompt(chunks: list[RetrievedChunk], *, label: str | None = None) -> str:
    if not chunks:
        return ""
    header = label or "Retrieved evidence (cite when relevant)"
    lines = [f"{header}:"]
    lines.extend(f"- {c.to_prompt_line()}" for c in chunks)
    return "\n".join(lines)


def chunks_to_citations(chunks: list[RetrievedChunk]) -> list[dict]:
    return [c.to_citation().model_dump() for c in chunks]
