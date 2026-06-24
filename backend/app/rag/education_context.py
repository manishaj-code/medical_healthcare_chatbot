"""RAG context helpers for education specialist."""
from __future__ import annotations

from app.database import get_settings
from app.multi_agent.types import AgentContext
from app.rag.retriever import chunks_to_citations, format_chunks_for_prompt, retrieve_evidence
from app.rag.schemas import IndexType


async def load_education_rag_context(ctx: AgentContext) -> tuple[str, list[dict]]:
    settings = get_settings()
    if not settings.rag_enabled:
        return "", []

    chunks = await retrieve_evidence(
        ctx.db,
        query=ctx.text,
        indexes=[IndexType.CLINICAL_KB],
        patient_id=ctx.patient.id if ctx.patient else None,
        top_k=settings.rag_top_k,
    )
    if not chunks:
        return "", []

    block = format_chunks_for_prompt(chunks, label="Retrieved clinical guidelines (cite when used)")
    return block, chunks_to_citations(chunks)
