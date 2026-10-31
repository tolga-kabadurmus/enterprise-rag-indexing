"""Shared lifecycle contract for infrastructure repositories."""

from abc import ABC, abstractmethod


class Repository(ABC):
    """Small asynchronous cleanup contract for external-service adapters."""

    @abstractmethod
    async def close(self) -> None:
        """Release external clients; repeated calls must be safe."""
