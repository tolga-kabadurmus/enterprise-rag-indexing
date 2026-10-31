"""Provider-neutral vector persistence contract and point models."""

from abc import abstractmethod

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.repository.base import Repository


class SparseVector(BaseModel):
    """One sparse vector represented by aligned term indexes and values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    indices: tuple[int, ...]
    values: tuple[float, ...]

    @model_validator(mode="after")
    def validate_alignment(self) -> "SparseVector":
        """Reject malformed sparse vectors before provider persistence."""

        if not self.indices or len(self.indices) != len(self.values):
            raise ValueError("sparse indices and values must be non-empty and aligned")
        return self


class VectorPoint(BaseModel):
    """One deterministic dense point with citation payload and optional sparse data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    point_id: str = Field(min_length=1)
    dense_vector: tuple[float, ...] = Field(min_length=1)
    payload: dict[str, object]
    sparse_vector: SparseVector | None = None


class VectorRepositoryBase(Repository):
    """Persist and manage vectors without exposing the selected provider."""

    @abstractmethod
    async def ensure_collection(self) -> None:
        """Create storage idempotently or validate its vector schema."""

    @abstractmethod
    async def upsert_points(self, points: tuple[VectorPoint, ...]) -> None:
        """Upsert deterministic points in bounded, retryable batches."""
