"""RAG data types."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class IndexType(str, Enum):
    PATIENT_CHART = "patient_chart"
    CLINICAL_KB = "clinical_kb"
    REPORT = "report"
    TRANSCRIPT = "transcript"


class Citation(BaseModel):
    source_id: str
    title: str
    excerpt: str
    index_type: str
    score: float | None = None


class RetrievedChunk(BaseModel):
    id: str
    index_type: str
    source_id: str
    title: str
    content: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_citation(self) -> Citation:
        excerpt = self.content if len(self.content) <= 280 else self.content[:277] + "..."
        return Citation(
            source_id=self.source_id,
            title=self.title,
            excerpt=excerpt,
            index_type=self.index_type,
            score=self.score,
        )

    def to_prompt_line(self) -> str:
        return f"[{self.title}] {self.content}"
