"""Document indexer contract and citation-ready processing models."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.chunkers.base import DocumentChunk
from app.repository.models import S3ObjectMetadata


class LocalDocument(BaseModel):
    """A processing object downloaded into the ephemeral job workspace."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_metadata: S3ObjectMetadata
    processing_metadata: S3ObjectMetadata
    local_path: Path


class DocumentIndexingResult(BaseModel):
    """Text-chunking outcome returned before embedding or persistence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_metadata: S3ObjectMetadata
    processing_metadata: S3ObjectMetadata
    status: Literal["chunked", "empty"]
    chunks: tuple[DocumentChunk, ...] = ()
    detail: str = Field(min_length=1)

    @computed_field
    @property
    def chunk_count(self) -> int:
        """Return the number of chunks available for the embedding stage."""

        return len(self.chunks)


class DocumentIndexer(ABC):
    """Process one local object through a content-specific boundary."""

    @abstractmethod
    async def index(self, document: LocalDocument) -> DocumentIndexingResult:
        """Extract and chunk one document without persisting vectors."""
