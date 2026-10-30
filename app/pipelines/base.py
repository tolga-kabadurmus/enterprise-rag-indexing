"""Shared startup and cleanup behavior for real indexing pipelines."""

from abc import abstractmethod
import logging

from app.common.settings.embeddings import EmbeddingModelSettings
from app.jobs.base import AsyncIndexingJob, IndexingJobArguments
from app.repository.s3.base import S3Repository

LOGGER = logging.getLogger(__name__)


class BasePipeline(AsyncIndexingJob):
    """Download embedding model artifacts before pipeline-specific work.

    Concrete production pipelines inherit this class and implement ``run``.
    They may override the two resource hooks, but should not override
    ``initialize`` or ``close`` because those methods enforce model sync and
    repository cleanup order. The side-effect-free mock job intentionally
    continues to inherit :class:`AsyncIndexingJob` directly.

    Args:
        arguments: Validated source selection and concurrency settings.
        s3_repository: Initialized S3 infrastructure adapter.
        embedding_settings: Configurable remote and local model locations.
    """

    def __init__(
        self,
        arguments: IndexingJobArguments,
        s3_repository: S3Repository,
        embedding_settings: EmbeddingModelSettings,
    ) -> None:
        super().__init__(arguments)
        self.s3_repository = s3_repository
        self.embedding_settings = embedding_settings
        self.embedding_files: list[str] = []
        self._initialized = False

    async def initialize(self) -> None:
        """Validate work before synchronizing and loading model resources."""

        should_initialize_model = await self.prepare_pipeline()
        if should_initialize_model:
            await self._initialize_embedding_resources()
        self._initialized = True

    async def prepare_pipeline(self) -> bool:
        """Prepare work before expensive embedding initialization.

        Returns:
            ``True`` when the pipeline has work requiring model resources.
            The default preserves model initialization for pipelines without a
            discovery phase. Concrete pipelines may return ``False`` for an
            empty, successfully validated selection.
        """

        return True

    async def _initialize_embedding_resources(self) -> None:
        """Synchronize embedding artifacts and initialize model resources."""

        settings = self.embedding_settings
        LOGGER.info(
            "synchronizing embedding model bucket=%s key_prefix=%s destination=%s",
            settings.bucket,
            settings.key_prefix,
            settings.local_directory,
        )
        paths = await self.s3_repository.download_prefix(
            settings.bucket,
            settings.key_prefix,
            settings.local_directory,
        )
        if not paths:
            raise RuntimeError(
                "embedding model prefix contains no downloadable files: "
                f"s3://{settings.bucket}/{settings.key_prefix}/"
            )
        self.embedding_files = [str(path) for path in paths]
        await self.initialize_pipeline_resources()

    async def initialize_pipeline_resources(self) -> None:
        """Optional hook run after embedding model artifacts are available."""

    @abstractmethod
    async def run(self) -> None:
        """Execute one pipeline batch after successful model synchronization."""

    async def close_pipeline_resources(self) -> None:
        """Optional idempotent hook for concrete pipeline resource cleanup."""

    async def close(self) -> None:
        """Close pipeline resources and always close the S3 repository."""

        try:
            await self.close_pipeline_resources()
        finally:
            self._initialized = False
            await self.s3_repository.close()
