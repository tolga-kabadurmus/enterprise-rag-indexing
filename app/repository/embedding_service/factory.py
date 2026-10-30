"""Registry-based factory for embedding repository providers."""

from typing import Any, TypeVar

from app.common.settings.embedding_service import EmbeddingProvider
from app.repository.embedding_service.base import EmbeddingRepository

EmbeddingRepositoryType = TypeVar(
    "EmbeddingRepositoryType",
    bound=EmbeddingRepository,
)


class EmbeddingRepositoryFactory:
    """Register and construct implementations of the embedding capability."""

    def __init__(self) -> None:
        self._providers: dict[EmbeddingProvider, type[EmbeddingRepository]] = {}

    def register(
        self,
        provider: EmbeddingProvider,
        repository_type: type[EmbeddingRepositoryType],
    ) -> None:
        """Register one embedding implementation under an enum provider key."""

        if not issubclass(repository_type, EmbeddingRepository):
            raise TypeError("embedding repository must inherit EmbeddingRepository")
        if provider in self._providers:
            raise ValueError(
                f"embedding provider is already registered: {provider.value}"
            )
        self._providers[provider] = repository_type

    def create(
        self,
        provider: EmbeddingProvider,
        *args: Any,
        **kwargs: Any,
    ) -> EmbeddingRepository:
        """Construct the implementation registered for ``provider``."""

        repository_type = self._providers.get(provider)
        if repository_type is None:
            raise ValueError(f"unsupported embedding provider: {provider.value}")
        return repository_type(*args, **kwargs)
