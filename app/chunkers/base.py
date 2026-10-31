"""Document chunking contract and citation-ready output models."""

from abc import ABC, abstractmethod
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    model_validator,
)

from app.document_extractors.models import ExtractedPage
from app.repository.models import S3ObjectMetadata


class DocumentChunk(BaseModel):
    """One text chunk and the complete metadata needed for RAG citation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source_bucket: str = Field(min_length=1)
    object_key: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    chunk_index: int = Field(ge=0)
    page_chunk_index: int = Field(ge=0)
    character_start: int = Field(ge=0)
    character_end: int = Field(gt=0)
    content_type: str | None = None
    etag: str | None = None
    processing_bucket: str = Field(min_length=1)
    processing_object_key: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_character_range(self) -> Self:
        """Require a non-empty normalized-text character range."""

        if self.character_end <= self.character_start:
            raise ValueError("character_end must be greater than character_start")
        return self


class ChunkingResult(BaseModel):
    """Text chunks returned without embeddings or persistence claims."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["chunked", "empty"]
    chunks: tuple[DocumentChunk, ...] = ()
    detail: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_status_matches_chunks(self) -> Self:
        """Prevent empty results from claiming chunks and vice versa."""

        if self.status == "chunked" and not self.chunks:
            raise ValueError("chunked result must contain at least one chunk")
        if self.status == "empty" and self.chunks:
            raise ValueError("empty result must not contain chunks")
        return self

    @computed_field
    @property
    def chunk_count(self) -> int:
        """Return the number of citation-ready chunks."""

        return len(self.chunks)


class DocumentChunker(ABC):
    """Behavior contract implemented by versioned document chunkers."""

    @abstractmethod
    async def chunk(
        self,
        source_metadata: S3ObjectMetadata,
        processing_metadata: S3ObjectMetadata,
        pages: tuple[ExtractedPage, ...],
    ) -> ChunkingResult:
        """Create citation-ready chunks from already extracted page text."""
