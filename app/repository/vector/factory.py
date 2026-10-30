"""Registry-based factory for vector repository providers."""

from typing import Any, TypeVar

from app.repository.vector.base import VectorRepositoryBase

VectorRepositoryType = TypeVar(
    "VectorRepositoryType",
    bound=VectorRepositoryBase,
)


class VectorRepositoryFactory:
    """Register and construct implementations of the vector capability."""

    def __init__(self) -> None:
        self._providers: dict[str, type[VectorRepositoryBase]] = {}

    def register(
        self,
        provider: str,
        repository_type: type[VectorRepositoryType],
    ) -> None:
        """Register one vector implementation under a stable provider key.

        Args:
            provider: Configuration key used to select the implementation.
            repository_type: Concrete class implementing ``VectorRepositoryBase``.

        Raises:
            TypeError: If the registered class does not implement the vector contract.
            ValueError: If the provider key is empty or already registered.
        """

        key = self._normalize_provider(provider)
        if not issubclass(repository_type, VectorRepositoryBase):
            raise TypeError("vector repository must inherit VectorRepositoryBase")
        if key in self._providers:
            raise ValueError(f"vector provider is already registered: {key}")
        self._providers[key] = repository_type

    def create(
        self,
        provider: str,
        *args: Any,
        **kwargs: Any,
    ) -> VectorRepositoryBase:
        """Construct the implementation registered for ``provider``.

        Constructor dependencies remain explicit at the application composition
        layer and are forwarded unchanged to the selected implementation.

        Raises:
            ValueError: If no implementation is registered for the provider.
        """

        key = self._normalize_provider(provider)
        repository_type = self._providers.get(key)
        if repository_type is None:
            raise ValueError(f"unsupported vector provider: {key}")
        return repository_type(*args, **kwargs)

    @staticmethod
    def _normalize_provider(provider: str) -> str:
        key = provider.strip().lower()
        if not key:
            raise ValueError("vector provider must not be empty")
        return key
