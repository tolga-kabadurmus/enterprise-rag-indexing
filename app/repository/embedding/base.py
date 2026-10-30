"""Embedding model runtime repository contract."""

from abc import abstractmethod
from pathlib import Path

from app.repository.base import Repository


class EmbeddingModelRepository(Repository):
    """Manage the lifecycle of one locally stored embedding model."""

    @property
    @abstractmethod
    def is_loaded(self) -> bool:
        """Return whether a model runtime session is ready."""

    @abstractmethod
    async def load(self, model_path: Path) -> None:
        """Load a model artifact once from ``model_path``."""
