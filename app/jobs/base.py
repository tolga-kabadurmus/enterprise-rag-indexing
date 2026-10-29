"""Base contract for one-shot asynchronous indexing jobs."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import TracebackType


@dataclass(frozen=True, slots=True)
class IndexingJobArguments:
    """Validated object selection and concurrency settings for an indexing job.

    An exact object key and a key prefix are mutually exclusive. When both are
    omitted, a concrete job may discover every eligible object in the source
    bucket.

    Attributes:
        source_bucket: S3-compatible bucket containing source documents.
        object_key: Exact object key to index, if a single object was selected.
        key_prefix: Prefix used to discover eligible object keys.
        concurrency: Maximum number of documents processed concurrently.

    Raises:
        ValueError: If the bucket is empty, the selectors conflict, or the
            concurrency value is less than one.
    """

    source_bucket: str
    object_key: str | None = None
    key_prefix: str | None = None
    concurrency: int = 4

    def __post_init__(self) -> None:
        if not self.source_bucket.strip():
            raise ValueError("source_bucket must not be empty")
        if self.object_key is not None and not self.object_key:
            raise ValueError("object_key must not be empty")
        if self.object_key is not None and self.key_prefix is not None:
            raise ValueError("object_key and key_prefix are mutually exclusive")
        if self.concurrency < 1:
            raise ValueError("concurrency must be at least 1")


class AsyncIndexingJob(ABC):
    """Lifecycle contract implemented by each document indexing job.

    Concrete jobs acquire repositories and provider clients in `initialize`,
    perform one batch in `run`, and release every acquired resource in `close`.
    Callers should use `execute_job` rather than invoking these methods directly.

    Args:
        arguments: Validated source selection and concurrency settings.
    """

    def __init__(self, arguments: IndexingJobArguments) -> None:
        self.arguments = arguments

    async def __aenter__(self) -> "AsyncIndexingJob":
        """Initialize the job and return it as an async context manager.

        Returns:
            The initialized job.

        Raises:
            BaseException: Re-raises initialization failures after attempting
                resource cleanup.
        """

        try:
            await self.initialize()
        except BaseException:
            await self.close()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        """Close resources without suppressing an active exception.

        Returns:
            Always `False`, so exceptions from the job propagate to the caller.
        """

        await self.close()
        return False

    async def initialize(self) -> None:
        """Initialize repositories and other resources before execution.

        The default implementation is a no-op for jobs without managed
        resources. Implementations should assign resources incrementally so
        `close` can safely clean up after partial initialization.
        """

    @abstractmethod
    async def run(self) -> None:
        """Perform one indexing batch and then return.

        Implementations must not turn this method into a permanent worker loop.
        """

    async def close(self) -> None:
        """Release resources.

        Implementations must make cleanup idempotent because this method also
        runs after partial initialization failures.
        """
