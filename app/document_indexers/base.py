"""Document indexer contract and processing result models."""

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.repository.models import S3ObjectMetadata


class DocumentIndexingResult(BaseModel):
    """Outcome returned by a content-type-specific document indexer."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    metadata: S3ObjectMetadata
    status: Literal["not_implemented"]
    chunk_count: int = Field(default=0, ge=0)
    detail: str = Field(min_length=1)


class DocumentIndexer(ABC):
    """Process one object through its content-type-specific boundary."""

    @abstractmethod
    async def index(
        self,
        metadata: S3ObjectMetadata,
    ) -> DocumentIndexingResult:
        """Process one object and return a truthful indexing status."""
