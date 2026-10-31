"""Embedding service repository contract."""

from abc import abstractmethod
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.repository.base import Repository


class SparseEmbedding(BaseModel):
    """One sparse text representation with aligned token IDs and weights."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    indices: tuple[int, ...]
    values: tuple[float, ...]

    @model_validator(mode="after")
    def validate_alignment(self) -> "SparseEmbedding":
        """Reject empty, unaligned, or duplicate sparse entries."""

        if not self.indices or len(self.indices) != len(self.values):
            raise ValueError("sparse indices and values must be non-empty and aligned")
        if len(set(self.indices)) != len(self.indices):
            raise ValueError("sparse indices must be unique")
        return self

    @field_validator("indices")
    @classmethod
    def validate_indices(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        """Require non-negative sorted token IDs."""

        if any(index < 0 for index in value):
            raise ValueError("sparse indices must be non-negative")
        if tuple(sorted(value)) != value:
            raise ValueError("sparse indices must be sorted")
        return value

    @field_validator("values")
    @classmethod
    def validate_values(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        """Require finite positive term-frequency weights."""

        if any(not math.isfinite(weight) or weight <= 0 for weight in value):
            raise ValueError("sparse values must be finite and positive")
        return value


class EmbeddingVector(BaseModel):
    """Aligned dense and sparse representations for one input text."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dense: tuple[float, ...]
    sparse: SparseEmbedding

    @field_validator("dense")
    @classmethod
    def validate_dense(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        """Reject empty or non-finite dense vectors."""

        if not value or any(not math.isfinite(component) for component in value):
            raise ValueError("dense vector must be non-empty and finite")
        return value


class EmbeddingRepository(Repository):
    """Generate vectors through the configured embedding provider."""

    @property
    @abstractmethod
    def max_batch_size(self) -> int:
        """Return the maximum number of texts accepted in one request."""

    @property
    @abstractmethod
    def max_text_characters(self) -> int:
        """Return the maximum aggregate characters accepted per request."""

    @abstractmethod
    async def embed(
        self,
        texts: tuple[str, ...],
        input_type: Literal["document", "query"] = "document",
    ) -> tuple[EmbeddingVector, ...]:
        """Return aligned dense and sparse vectors for each input text."""
