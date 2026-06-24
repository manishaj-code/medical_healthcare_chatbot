"""Clinical knowledge base seed and indexing."""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag_chunk import RagChunk
from app.rag.embeddings import get_embedding_provider
from app.rag.indexer import IndexDocument
from app.rag.schemas import IndexType

_SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "clinical_kb" / "seed.json"


def load_clinical_kb_documents() -> list[IndexDocument]:
    raw = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    docs: list[IndexDocument] = []
    for row in raw:
        source_id = str(row["source_id"]).strip()
        title = str(row["title"]).strip()
        content = str(row["content"]).strip()
        if not source_id or not content:
            continue
        docs.append(
            IndexDocument(
                source_id=source_id,
                title=title,
                content=content,
                metadata={
                    "topic": row.get("topic") or "general",
                    "source": row.get("source") or "clinical_kb",
                    "category": "guideline",
                },
            )
        )
    return docs


async def upsert_clinical_kb_index(db: AsyncSession) -> int:
    documents = load_clinical_kb_documents()
    if not documents:
        return 0

    provider = get_embedding_provider()
    embeddings = await provider.embed_batch([d.content for d in documents])

    await db.execute(delete(RagChunk).where(RagChunk.index_type == IndexType.CLINICAL_KB.value))

    for doc, embedding in zip(documents, embeddings, strict=True):
        db.add(
            RagChunk(
                index_type=IndexType.CLINICAL_KB.value,
                patient_id=None,
                source_id=doc.source_id,
                title=doc.title,
                content=doc.content,
                chunk_metadata=doc.metadata,
                embedding=embedding,
            )
        )

    await db.flush()
    return len(documents)
