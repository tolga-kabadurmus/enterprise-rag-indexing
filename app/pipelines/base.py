"""Shared startup and cleanup behavior for real indexing pipelines."""

from abc import abstractmethod
import logging

from app.jobs.base import AsyncIndexingJob, IndexingJobArguments
from app.repository.s3.base import S3Repository
from app.repository.embedding_service.base import EmbeddingRepository

LOGGER = logging.getLogger(__name__)


class BasePipeline(AsyncIndexingJob):
    """Coordinate shared initialization and cleanup for real pipelines.

    Concrete production pipelines inherit this class and implement ``run``.
    They may override the two resource hooks, but should not override
    ``initialize`` or ``close`` because those methods enforce source
    preparation and repository cleanup order. The side-effect-free mock job intentionally
    continues to inherit :class:`AsyncIndexingJob` directly.

    Args:
        arguments: Validated source selection and concurrency settings.
        s3_repository: Initialized S3 infrastructure adapter.
        embedding_repository: Shared embedding-service adapter.
    """

    def __init__(
        self,
        arguments: IndexingJobArguments,
        s3_repository: S3Repository,
        embedding_repository: EmbeddingRepository,
    ) -> None:
        super().__init__(arguments)
        self.s3_repository = s3_repository
        self.embedding_repository = embedding_repository
        self._initialized = False

    async def initialize(self) -> None:
        """Validate work before initializing pipeline-specific resources."""

        should_initialize_model = await self.prepare_pipeline()
        if should_initialize_model:
            await self.initialize_pipeline_resources()
        self._initialized = True

    async def prepare_pipeline(self) -> bool:
        """Prepare work before expensive embedding initialization.

        Returns:
            ``True`` when the pipeline has work requiring embedding resources.
            The default preserves model initialization for pipelines without a
            discovery phase. Concrete pipelines may return ``False`` for an
            empty, successfully validated selection.
        """

        return True

    async def initialize_pipeline_resources(self) -> None:
        """Optionally initialize pipeline-specific resources."""

    @abstractmethod
    async def run(self) -> None:
        """Execute one pipeline batch after successful resource initialization."""

    async def close_pipeline_resources(self) -> None:
        """Optional idempotent hook for concrete pipeline resource cleanup."""

    async def close(self) -> None:
        """Close pipeline resources and always close the S3 repository."""

        try:
            await self.close_pipeline_resources()
        finally:
            self._initialized = False
            try:
                await self.embedding_repository.close()
            finally:
                await self.s3_repository.close()
