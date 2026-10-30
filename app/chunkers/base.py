"""Document chunking contract and result models."""

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.repository.models import S3ObjectMetadata


class ChunkingResult(BaseModel):
    """Explicit result from a document chunking component."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["not_implemented"]
    chunk_count: int = Field(default=0, ge=0)
    detail: str = Field(min_length=1)


class DocumentChunker(ABC):
    """Behavior contract implemented by versioned document chunkers."""

    @abstractmethod
    async def chunk(self, metadata: S3ObjectMetadata) -> ChunkingResult:
        """Chunk one document or return an explicit incomplete status."""
