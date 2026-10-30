"""Explicitly unavailable local embedding compatibility provider."""

from typing import Literal

from app.repository.embedding_service.base import EmbeddingRepository


class FallBackLocalEmbeddingFactory(EmbeddingRepository):
    """Reject local embedding use until a supported implementation is approved."""

    @property
    def max_batch_size(self) -> int:
        """Reject use because local embedding is not implemented."""

        raise NotImplementedError("local embedding fallback is not implemented")

    @property
    def max_text_characters(self) -> int:
        """Reject use because local embedding is not implemented."""

        raise NotImplementedError("local embedding fallback is not implemented")

    async def embed(
        self,
        texts: tuple[str, ...],
        input_type: Literal["document", "query"] = "document",
    ) -> tuple[tuple[float, ...], ...]:
        """Reject vectorization because local embedding is not implemented."""

        raise NotImplementedError("local embedding fallback is not implemented")

    async def close(self) -> None:
        """Release nothing because the unimplemented fallback owns no resources."""
