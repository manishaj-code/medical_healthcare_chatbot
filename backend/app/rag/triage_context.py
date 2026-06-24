"""RAG context helpers for triage specialist."""
from __future__ import annotations

from app.database import get_settings
from app.multi_agent.types import AgentContext
from app.rag.retriever import chunks_to_citations, format_chunks_for_prompt, retrieve_evidence
from app.rag.schemas import IndexType


async def load_triage_rag_context(ctx: AgentContext) -> tuple[str, list[dict]]:
    settings = get_settings()
    if not settings.rag_enabled or ctx.patient is None:
        return "", []

    chunks = await retrieve_evidence(
        ctx.db,
        query=ctx.text,
        indexes=[IndexType.PATIENT_CHART],
        patient_id=ctx.patient.id,
        top_k=settings.rag_top_k,
    )
    if not chunks:
        return "", []

    block = format_chunks_for_prompt(chunks, label="Retrieved evidence from patient chart (cite when relevant)")
    return block, chunks_to_citations(chunks)


def attach_citations_to_response(response, citations: list[dict]):
    if not citations:
        return response
    ui = dict(response.ui or {})
    ui["citations"] = citations
    response.ui = ui
    return response
