"""Embedding service repository contract."""

from abc import abstractmethod
from typing import Literal

from app.repository.base import Repository


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
    ) -> tuple[tuple[float, ...], ...]:
        """Return one vector for each input text."""
