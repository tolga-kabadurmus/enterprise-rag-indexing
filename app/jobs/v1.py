"""Version-one S3 document discovery and routing pipeline."""

import asyncio
import logging
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.common.settings.embeddings import EmbeddingModelSettings
from app.common.utility.mime import normalize_content_type
from app.document_indexers.factory import (
    DocumentIndexerFactory,
    UnsupportedContentTypeError,
)
from app.jobs.base import IndexingJobArguments
from app.pipelines.base import BasePipeline
from app.repository.embedding.base import EmbeddingModelRepository
from app.repository.exceptions import S3ObjectNotFoundError
from app.repository.models import S3ObjectMetadata
from app.repository.s3.base import S3Repository

LOGGER = logging.getLogger(__name__)


class ObjectProcessingResult(BaseModel):
    """Per-object v1 routing outcome without fabricated indexing claims."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bucket: str = Field(min_length=1)
    object_key: str = Field(min_length=1)
    status: Literal["not_implemented", "unsupported", "failed"]
    normalized_content_type: str | None = None
    detail: str = Field(min_length=1)
    elapsed_seconds: float = Field(ge=0)


class V1BatchSummary(BaseModel):
    """Aggregate counts from one v1 pipeline invocation.

    ``processed`` counts objects that completed inspection without an
    exception, including unsupported and not-yet-implemented objects. It does
    not claim that chunks or vectors were produced.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    discovered: int = Field(ge=0)
    processed: int = Field(ge=0)
    not_implemented: int = Field(ge=0)
    unsupported: int = Field(ge=0)
    failed: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0)


class V1IndexingPipeline(BasePipeline):
    """Load one model and inspect selected S3 objects with bounded concurrency.

    This first version lists or resolves source objects, obtains complete
    metadata, normalizes content types, and routes PDFs to ``PDFChunkerV1``.
    PDF extraction, actual chunks, embedding inference, and Qdrant persistence
    are intentionally not implemented yet.
    """

    def __init__(
        self,
        arguments: IndexingJobArguments,
        s3_repository: S3Repository,
        embedding_settings: EmbeddingModelSettings,
        embedding_model_repository: EmbeddingModelRepository,
        document_indexer_factory: DocumentIndexerFactory,
    ) -> None:
        super().__init__(arguments, s3_repository, embedding_settings)
        self.embedding_model_repository = embedding_model_repository
        self.document_indexer_factory = document_indexer_factory
        self.results: list[ObjectProcessingResult] = []
        self.summary: V1BatchSummary | None = None
        self._selected_objects: list[S3ObjectMetadata] = []

    async def prepare_pipeline(self) -> bool:
        """Discover and validate source objects before model initialization."""

        self._selected_objects = await self._select_objects()
        LOGGER.info(
            "selected S3 objects bucket=%s object_key=%s key_prefix=%s count=%d",
            self.arguments.source_bucket,
            self.arguments.object_key,
            self.arguments.key_prefix,
            len(self._selected_objects),
        )
        return bool(self._selected_objects)

    async def initialize_pipeline_resources(self) -> None:
        """Load the configured embedding model once after artifact sync."""

        await self.embedding_model_repository.load(
            self.embedding_settings.model_path
        )

    async def run(self) -> None:
        """Inspect the exact object or every selected bucket object once."""

        if not self._initialized:
            raise RuntimeError("v1 indexing pipeline has not been initialized")
        if self._selected_objects and not self.embedding_model_repository.is_loaded:
            raise RuntimeError("embedding model is not loaded")

        started_at = asyncio.get_running_loop().time()
        semaphore = asyncio.Semaphore(self.arguments.concurrency)

        for offset in range(
            0,
            len(self._selected_objects),
            self.arguments.concurrency,
        ):
            batch = self._selected_objects[
                offset : offset + self.arguments.concurrency
            ]
            self.results.extend(
                await asyncio.gather(
                    *(
                        self._process_object(metadata, semaphore)
                        for metadata in batch
                    )
                )
            )

        elapsed_seconds = asyncio.get_running_loop().time() - started_at
        self.summary = V1BatchSummary(
            discovered=len(self._selected_objects),
            processed=sum(result.status != "failed" for result in self.results),
            not_implemented=sum(
                result.status == "not_implemented" for result in self.results
            ),
            unsupported=sum(
                result.status == "unsupported" for result in self.results
            ),
            failed=sum(result.status == "failed" for result in self.results),
            elapsed_seconds=elapsed_seconds,
        )
        LOGGER.info(
            "v1 indexing batch completed bucket=%s discovered=%d processed=%d "
            "not_implemented=%d unsupported=%d failed=%d elapsed_seconds=%.3f",
            self.arguments.source_bucket,
            self.summary.discovered,
            self.summary.processed,
            self.summary.not_implemented,
            self.summary.unsupported,
            self.summary.failed,
            self.summary.elapsed_seconds,
        )

    async def close_pipeline_resources(self) -> None:
        """Release the shared embedding model runtime."""

        await self.embedding_model_repository.close()

    async def _select_objects(self) -> list[S3ObjectMetadata]:
        if self.arguments.object_key is not None:
            metadata = await self.s3_repository.get_object_metadata(
                self.arguments.source_bucket,
                self.arguments.object_key,
            )
            return [metadata]

        return await self.s3_repository.list_objects(
            self.arguments.source_bucket,
            self.arguments.key_prefix,
        )

    async def _process_object(
        self,
        discovered_metadata: S3ObjectMetadata,
        semaphore: asyncio.Semaphore,
    ) -> ObjectProcessingResult:
        async with semaphore:
            started_at = asyncio.get_running_loop().time()
            normalized_content_type: str | None = None
            try:
                metadata = discovered_metadata
                if self.arguments.object_key is None:
                    metadata = await self.s3_repository.get_object_metadata(
                        discovered_metadata.bucket,
                        discovered_metadata.key,
                    )
                normalized_content_type = normalize_content_type(
                    metadata.content_type,
                    metadata.key,
                )
                LOGGER.info(
                    "inspecting S3 object bucket=%s object_key=%s size=%d "
                    "etag=%s content_type=%s normalized_content_type=%s "
                    "last_modified=%s",
                    metadata.bucket,
                    metadata.key,
                    metadata.size,
                    metadata.etag,
                    metadata.content_type,
                    normalized_content_type,
                    metadata.last_modified,
                )
                document_indexer = self.document_indexer_factory.create(
                    normalized_content_type
                )
                indexing_result = await document_indexer.index(metadata)
                elapsed_seconds = asyncio.get_running_loop().time() - started_at
                LOGGER.warning(
                    "document processing incomplete bucket=%s object_key=%s "
                    "status=%s chunks=%d detail=%s elapsed_seconds=%.3f",
                    metadata.bucket,
                    metadata.key,
                    indexing_result.status,
                    indexing_result.chunk_count,
                    indexing_result.detail,
                    elapsed_seconds,
                )
                return ObjectProcessingResult(
                    bucket=metadata.bucket,
                    object_key=metadata.key,
                    status=indexing_result.status,
                    normalized_content_type=normalized_content_type,
                    detail=indexing_result.detail,
                    elapsed_seconds=elapsed_seconds,
                )
            except UnsupportedContentTypeError as error:
                elapsed_seconds = asyncio.get_running_loop().time() - started_at
                LOGGER.warning(
                    "skipping unsupported object bucket=%s object_key=%s "
                    "content_type=%s elapsed_seconds=%.3f",
                    discovered_metadata.bucket,
                    discovered_metadata.key,
                    normalized_content_type,
                    elapsed_seconds,
                )
                return ObjectProcessingResult(
                    bucket=discovered_metadata.bucket,
                    object_key=discovered_metadata.key,
                    status="unsupported",
                    normalized_content_type=normalized_content_type,
                    detail=str(error),
                    elapsed_seconds=elapsed_seconds,
                )
            except S3ObjectNotFoundError as error:
                elapsed_seconds = asyncio.get_running_loop().time() - started_at
                LOGGER.error(
                    "object disappeared during processing bucket=%s "
                    "object_key=%s elapsed_seconds=%.3f reason=%s",
                    discovered_metadata.bucket,
                    discovered_metadata.key,
                    elapsed_seconds,
                    error,
                )
                return ObjectProcessingResult(
                    bucket=discovered_metadata.bucket,
                    object_key=discovered_metadata.key,
                    status="failed",
                    normalized_content_type=normalized_content_type,
                    detail=str(error),
                    elapsed_seconds=elapsed_seconds,
                )
            except Exception as error:
                elapsed_seconds = asyncio.get_running_loop().time() - started_at
                LOGGER.exception(
                    "object processing failed bucket=%s object_key=%s "
                    "elapsed_seconds=%.3f",
                    discovered_metadata.bucket,
                    discovered_metadata.key,
                    elapsed_seconds,
                )
                return ObjectProcessingResult(
                    bucket=discovered_metadata.bucket,
                    object_key=discovered_metadata.key,
                    status="failed",
                    normalized_content_type=normalized_content_type,
                    detail=str(error) or type(error).__name__,
                    elapsed_seconds=elapsed_seconds,
                )
