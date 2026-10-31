"""Registry-based factory for storage repository providers."""

from typing import Any, TypeVar

from app.common.settings.s3 import StorageProvider
from app.repository.s3.base import StorageRepositoryBase

StorageRepositoryType = TypeVar(
    "StorageRepositoryType",
    bound=StorageRepositoryBase,
)


class StorageRepositoryFactory:
    """Register and construct implementations of the storage capability."""

    def __init__(self) -> None:
        self._providers: dict[StorageProvider, type[StorageRepositoryBase]] = {}

    def register(
        self,
        provider: StorageProvider,
        repository_type: type[StorageRepositoryType],
    ) -> None:
        """Register one storage implementation under an enum provider key."""

        if not issubclass(repository_type, StorageRepositoryBase):
            raise TypeError("storage repository must inherit StorageRepositoryBase")
        if provider in self._providers:
            raise ValueError(f"storage provider is already registered: {provider.value}")
        self._providers[provider] = repository_type

    def create(
        self,
        provider: StorageProvider,
        *args: Any,
        **kwargs: Any,
    ) -> StorageRepositoryBase:
        """Construct the implementation registered for ``provider``."""

        repository_type = self._providers.get(provider)
        if repository_type is None:
            raise ValueError(f"unsupported storage provider: {provider.value}")
        return repository_type(*args, **kwargs)
