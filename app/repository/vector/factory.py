"""Registry-based factory for vector repository providers."""

from typing import Any, TypeVar

from app.common.settings.vector import VectorProvider
from app.repository.vector.base import VectorRepositoryBase

VectorRepositoryType = TypeVar(
    "VectorRepositoryType",
    bound=VectorRepositoryBase,
)


class VectorRepositoryFactory:
    """Register and construct implementations of the vector capability."""

    def __init__(self) -> None:
        self._providers: dict[VectorProvider, type[VectorRepositoryBase]] = {}

    def register(
        self,
        provider: VectorProvider,
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

        if not issubclass(repository_type, VectorRepositoryBase):
            raise TypeError("vector repository must inherit VectorRepositoryBase")
        if provider in self._providers:
            raise ValueError(f"vector provider is already registered: {provider.value}")
        self._providers[provider] = repository_type

    def create(
        self,
        provider: VectorProvider,
        *args: Any,
        **kwargs: Any,
    ) -> VectorRepositoryBase:
        """Construct the implementation registered for ``provider``.

        Constructor dependencies remain explicit at the application composition
        layer and are forwarded unchanged to the selected implementation.

        Raises:
            ValueError: If no implementation is registered for the provider.
        """

        repository_type = self._providers.get(provider)
        if repository_type is None:
            raise ValueError(f"unsupported vector provider: {provider.value}")
        return repository_type(*args, **kwargs)
