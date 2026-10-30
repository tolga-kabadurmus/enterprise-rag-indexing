"""Version-one claimed S3 PDF text-chunking pipeline."""

import asyncio
from datetime import datetime
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.chunkers.base import DocumentChunk
from app.common.settings.indexing import IndexingWorkspaceSettings
from app.common.settings.s3 import S3Settings
from app.common.utility.mime import normalize_content_type
from app.common.utility.processing_keys import (
    claim_object_key,
    error_object_key,
    is_error_object_key,
    original_key_from_processing_key,
    processing_object_key,
    processing_object_prefix,
)
from app.document_indexers.base import LocalDocument
from app.document_indexers.factory import (
    DocumentIndexerFactory,
    UnsupportedContentTypeError,
)
from app.jobs.base import IndexingJobArguments
from app.pipelines.base import BasePipeline
from app.repository.embedding_service.base import EmbeddingRepository
from app.repository.exceptions import S3ObjectNotFoundError
from app.repository.models import S3ObjectMetadata
from app.repository.s3.base import S3Repository
from app.repository.vector.base import VectorPoint, VectorRepositoryBase

LOGGER = logging.getLogger(__name__)


class SelectedDocument(BaseModel):
    """A discovered source identity that may already be in processing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_metadata: S3ObjectMetadata
    processing_metadata: S3ObjectMetadata | None = None
    source_exists: bool = True


class PreparedDocument(BaseModel):
    """A claimed durable processing copy ready for local download."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_metadata: S3ObjectMetadata
    processing_metadata: S3ObjectMetadata
    claim_key: str = Field(min_length=1)


class ObjectProcessingResult(BaseModel):
    """Per-object text-chunking outcome without persistence claims."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bucket: str = Field(min_length=1)
    object_key: str = Field(min_length=1)
    processing_bucket: str | None = None
    processing_object_key: str | None = None
    status: Literal[
        "chunked",
        "empty",
        "unsupported",
        "failed",
        "claimed_elsewhere",
    ]
    normalized_content_type: str | None = None
    chunks: tuple[DocumentChunk, ...] = ()
    embeddings: tuple[tuple[float, ...], ...] = ()
    detail: str = Field(min_length=1)
    elapsed_seconds: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_embedding_alignment(self) -> "ObjectProcessingResult":
        """Keep generated vectors positionally aligned with chunk metadata."""

        if self.embeddings and len(self.embeddings) != len(self.chunks):
            raise ValueError("embeddings must align one-to-one with chunks")
        return self


class V1BatchSummary(BaseModel):
    """Aggregate counts from one claimed v1 pipeline invocation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    discovered: int = Field(ge=0)
    processed: int = Field(ge=0)
    chunked: int = Field(ge=0)
    empty: int = Field(ge=0)
    unsupported: int = Field(ge=0)
    failed: int = Field(ge=0)
    claimed_elsewhere: int = Field(ge=0)
    chunk_count: int = Field(ge=0)
    vector_count: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0)


class V1IndexingPipeline(BasePipeline):
    """Claim, stage, extract, and chunk selected PDFs with bounded concurrency.

    Source objects are copied into the configured processing bucket and the
    source is deleted only after the durable copy's size is verified. Chunk
    vectors are persisted to Qdrant with citation metadata. A conditional S3
    claim prevents concurrent jobs from working on the same source identity
    during one attempt.
    """

    def __init__(
        self,
        arguments: IndexingJobArguments,
        s3_repository: S3Repository,
        s3_settings: S3Settings,
        workspace_settings: IndexingWorkspaceSettings,
        document_indexer_factory: DocumentIndexerFactory,
        embedding_repository: EmbeddingRepository,
        vector_repository: VectorRepositoryBase,
    ) -> None:
        super().__init__(
            arguments,
            s3_repository,
            embedding_repository=embedding_repository,
            vector_repository=vector_repository,
        )
        self.s3_settings = s3_settings
        self.workspace_settings = workspace_settings
        self.document_indexer_factory = document_indexer_factory
        self.results: list[ObjectProcessingResult] = []
        self.summary: V1BatchSummary | None = None
        self._prepared_documents: list[PreparedDocument] = []
        self._active_claims: set[str] = set()
        self._discovered_count = 0
        self._claim_owner = str(uuid4())

    @property
    def failed_count(self) -> int:
        """Return the number of objects that failed during the latest run."""

        return self.summary.failed if self.summary is not None else 0

    async def prepare_pipeline(self) -> bool:
        """Discover, claim, and move work before expensive model startup."""

        await self.s3_repository.ensure_bucket(
            self.s3_settings.processing_bucket
        )
        self.workspace_settings.work_directory.mkdir(parents=True, exist_ok=True)
        selected = await self._select_objects()
        self._discovered_count = len(selected)
        LOGGER.info(
            "selected S3 objects bucket=%s object_key=%s key_prefix=%s count=%d",
            self.arguments.source_bucket,
            self.arguments.object_key,
            self.arguments.key_prefix,
            len(selected),
        )

        for offset in range(0, len(selected), self.arguments.concurrency):
            batch = selected[offset : offset + self.arguments.concurrency]
            outcomes = await asyncio.gather(
                *(self._prepare_document(item) for item in batch)
            )
            for outcome in outcomes:
                if isinstance(outcome, PreparedDocument):
                    self._prepared_documents.append(outcome)
                else:
                    self.results.append(outcome)

        return bool(self._prepared_documents)

    async def run(self) -> None:
        """Download and text-chunk each claimed processing object once."""

        if not self._initialized:
            raise RuntimeError("v1 indexing pipeline has not been initialized")

        started_at = asyncio.get_running_loop().time()
        semaphore = asyncio.Semaphore(self.arguments.concurrency)
        for offset in range(
            0,
            len(self._prepared_documents),
            self.arguments.concurrency,
        ):
            batch = self._prepared_documents[
                offset : offset + self.arguments.concurrency
            ]
            self.results.extend(
                await asyncio.gather(
                    *(self._process_object(item, semaphore) for item in batch)
                )
            )

        elapsed_seconds = asyncio.get_running_loop().time() - started_at
        self.summary = V1BatchSummary(
            discovered=self._discovered_count,
            processed=sum(
                item.status in {"chunked", "empty", "unsupported"}
                for item in self.results
            ),
            chunked=sum(item.status == "chunked" for item in self.results),
            empty=sum(item.status == "empty" for item in self.results),
            unsupported=sum(
                item.status == "unsupported" for item in self.results
            ),
            failed=sum(item.status == "failed" for item in self.results),
            claimed_elsewhere=sum(
                item.status == "claimed_elsewhere" for item in self.results
            ),
            chunk_count=sum(len(item.chunks) for item in self.results),
            vector_count=sum(len(item.embeddings) for item in self.results),
            elapsed_seconds=elapsed_seconds,
        )
        LOGGER.info(
            "v1 indexing batch completed bucket=%s discovered=%d processed=%d "
            "chunked=%d empty=%d unsupported=%d failed=%d "
            "claimed_elsewhere=%d chunks=%d vectors=%d elapsed_seconds=%.3f",
            self.arguments.source_bucket,
            self.summary.discovered,
            self.summary.processed,
            self.summary.chunked,
            self.summary.empty,
            self.summary.unsupported,
            self.summary.failed,
            self.summary.claimed_elsewhere,
            self.summary.chunk_count,
            self.summary.vector_count,
            self.summary.elapsed_seconds,
        )

    async def close_pipeline_resources(self) -> None:
        """Release model resources and every claim surviving partial startup."""

        release_errors: list[Exception] = []
        for claim_key in tuple(self._active_claims):
            try:
                await self._release_claim(claim_key)
            except Exception as error:
                release_errors.append(error)
        if release_errors:
            raise RuntimeError(
                f"failed to release {len(release_errors)} S3 claims"
            ) from release_errors[0]

    async def _select_objects(self) -> list[SelectedDocument]:
        if self.arguments.object_key is not None:
            return [await self._select_exact_object(self.arguments.object_key)]

        source_objects, processing_objects = await asyncio.gather(
            self.s3_repository.list_objects(
                self.arguments.source_bucket,
                self.arguments.key_prefix,
            ),
            self.s3_repository.list_objects(
                self.s3_settings.processing_bucket,
                processing_object_prefix(
                    self.arguments.source_bucket,
                    self.arguments.key_prefix,
                ),
            ),
        )
        selected: dict[str, SelectedDocument] = {}
        for processing in processing_objects:
            original_key = original_key_from_processing_key(
                self.arguments.source_bucket,
                processing.key,
            )
            selected[original_key] = SelectedDocument(
                source_metadata=self._source_from_processing(
                    original_key,
                    processing,
                ),
                processing_metadata=processing,
                source_exists=False,
            )
        for source in source_objects:
            if self.arguments.key_prefix is None and is_error_object_key(source.key):
                continue
            existing = selected.get(source.key)
            selected[source.key] = SelectedDocument(
                source_metadata=source,
                processing_metadata=(
                    existing.processing_metadata if existing else None
                ),
                source_exists=True,
            )
        return list(selected.values())

    async def _select_exact_object(self, object_key: str) -> SelectedDocument:
        destination_key = processing_object_key(
            self.arguments.source_bucket,
            object_key,
        )
        processing_metadata: S3ObjectMetadata | None = None
        try:
            processing_metadata = await self.s3_repository.get_object_metadata(
                self.s3_settings.processing_bucket,
                destination_key,
            )
        except S3ObjectNotFoundError:
            pass

        try:
            source_metadata = await self.s3_repository.get_object_metadata(
                self.arguments.source_bucket,
                object_key,
            )
        except S3ObjectNotFoundError:
            if processing_metadata is None:
                raise
            return SelectedDocument(
                source_metadata=self._source_from_processing(
                    object_key,
                    processing_metadata,
                ),
                processing_metadata=processing_metadata,
                source_exists=False,
            )
        return SelectedDocument(
            source_metadata=source_metadata,
            processing_metadata=processing_metadata,
            source_exists=True,
        )

    async def _prepare_document(
        self,
        selected: SelectedDocument,
    ) -> PreparedDocument | ObjectProcessingResult:
        started_at = asyncio.get_running_loop().time()
        source = selected.source_metadata
        claim_key = claim_object_key(source.bucket, source.key)
        try:
            acquired = await self.s3_repository.try_acquire_claim(
                self.s3_settings.processing_bucket,
                claim_key,
                self._claim_owner,
                self.s3_settings.claim_ttl_seconds,
            )
            if not acquired:
                return self._result(
                    source,
                    selected.processing_metadata,
                    "claimed_elsewhere",
                    "another indexing job owns the conditional S3 claim",
                    started_at,
                )
            self._active_claims.add(claim_key)

            source_metadata = source
            if selected.source_exists:
                source_metadata = await self.s3_repository.get_object_metadata(
                    source.bucket,
                    source.key,
                )
            processing_metadata = selected.processing_metadata
            if processing_metadata is not None:
                processing_metadata = (
                    await self.s3_repository.get_object_metadata(
                        self.s3_settings.processing_bucket,
                        processing_metadata.key,
                    )
                )
                if not selected.source_exists:
                    source_metadata = self._source_from_processing(
                        source.key,
                        processing_metadata,
                    )
            else:
                processing_metadata = await self.s3_repository.copy_object(
                    source_metadata.bucket,
                    source_metadata.key,
                    self.s3_settings.processing_bucket,
                    processing_object_key(
                        source_metadata.bucket,
                        source_metadata.key,
                    ),
                    source_metadata.content_type,
                    self._processing_user_metadata(source_metadata),
                )

            if processing_metadata.size != source_metadata.size:
                raise RuntimeError(
                    "processing copy size does not match source: "
                    f"s3://{source_metadata.bucket}/{source_metadata.key}"
                )
            if selected.source_exists:
                await self.s3_repository.delete_object(
                    source_metadata.bucket,
                    source_metadata.key,
                )
            LOGGER.info(
                "claimed processing object source_bucket=%s object_key=%s "
                "processing_bucket=%s processing_object_key=%s",
                source_metadata.bucket,
                source_metadata.key,
                processing_metadata.bucket,
                processing_metadata.key,
            )
            return PreparedDocument(
                source_metadata=source_metadata,
                processing_metadata=processing_metadata,
                claim_key=claim_key,
            )
        except Exception as error:
            if claim_key in self._active_claims:
                await self._release_claim(claim_key)
            LOGGER.exception(
                "failed to prepare processing object bucket=%s object_key=%s",
                source.bucket,
                source.key,
            )
            return self._result(
                source,
                selected.processing_metadata,
                "failed",
                str(error) or type(error).__name__,
                started_at,
            )

    async def _process_object(
        self,
        document: PreparedDocument,
        semaphore: asyncio.Semaphore,
    ) -> ObjectProcessingResult:
        async with semaphore:
            started_at = asyncio.get_running_loop().time()
            normalized_content_type: str | None = None
            try:
                normalized_content_type = normalize_content_type(
                    document.source_metadata.content_type,
                    document.source_metadata.key,
                )
                indexer = self.document_indexer_factory.create(
                    normalized_content_type
                )
                with TemporaryDirectory(
                    prefix="document-",
                    dir=self.workspace_settings.work_directory,
                ) as temporary_directory:
                    local_path = Path(temporary_directory) / "source.pdf"
                    await self.s3_repository.download_object(
                        document.processing_metadata.bucket,
                        document.processing_metadata.key,
                        local_path,
                    )
                    indexing_result = await indexer.index(
                        LocalDocument(
                            source_metadata=document.source_metadata,
                            processing_metadata=document.processing_metadata,
                            local_path=local_path,
                        )
                    )
                embeddings: tuple[tuple[float, ...], ...] = ()
                if indexing_result.chunks:
                    try:
                        embeddings = await self._embed_chunks(
                            indexing_result.chunks
                        )
                        await self._upsert_chunks(
                            indexing_result.chunks,
                            embeddings,
                        )
                    except Exception as persistence_error:
                        error_metadata = await self._move_to_error_prefix(document)
                        LOGGER.exception(
                            "vectorization or Qdrant upsert failed; moved "
                            "document to error prefix "
                            "source_bucket=%s object_key=%s error_object_key=%s",
                            document.source_metadata.bucket,
                            document.source_metadata.key,
                            error_metadata.key,
                        )
                        return self._result(
                            document.source_metadata,
                            error_metadata,
                            "failed",
                            str(persistence_error)
                            or type(persistence_error).__name__,
                            started_at,
                            normalized_content_type,
                            indexing_result.chunks,
                        )
                LOGGER.info(
                    "PDF processing completed bucket=%s object_key=%s "
                    "status=%s chunks=%d vectors=%d elapsed_seconds=%.3f",
                    document.source_metadata.bucket,
                    document.source_metadata.key,
                    indexing_result.status,
                    indexing_result.chunk_count,
                    len(embeddings),
                    asyncio.get_running_loop().time() - started_at,
                )
                return self._result(
                    document.source_metadata,
                    document.processing_metadata,
                    indexing_result.status,
                    indexing_result.detail,
                    started_at,
                    normalized_content_type,
                    indexing_result.chunks,
                    embeddings,
                )
            except UnsupportedContentTypeError as error:
                LOGGER.warning(
                    "skipping unsupported processing object bucket=%s "
                    "object_key=%s content_type=%s",
                    document.source_metadata.bucket,
                    document.source_metadata.key,
                    normalized_content_type,
                )
                return self._result(
                    document.source_metadata,
                    document.processing_metadata,
                    "unsupported",
                    str(error),
                    started_at,
                    normalized_content_type,
                )
            except Exception as error:
                LOGGER.exception(
                    "object processing failed bucket=%s object_key=%s",
                    document.source_metadata.bucket,
                    document.source_metadata.key,
                )
                return self._result(
                    document.source_metadata,
                    document.processing_metadata,
                    "failed",
                    str(error) or type(error).__name__,
                    started_at,
                    normalized_content_type,
                )
            finally:
                await self._release_claim(
                    document.claim_key,
                    suppress_errors=True,
                )

    async def _embed_chunks(
        self,
        chunks: tuple[DocumentChunk, ...],
    ) -> tuple[tuple[float, ...], ...]:
        """Vectorize chunks in bounded batches through the shared service."""

        batch_size = self.embedding_repository.max_batch_size
        max_text_characters = self.embedding_repository.max_text_characters
        vectors: list[tuple[float, ...]] = []
        batch: list[DocumentChunk] = []
        batch_characters = 0
        for chunk in chunks:
            chunk_characters = len(chunk.text)
            if chunk_characters > max_text_characters:
                raise ValueError(
                    f"chunk {chunk.chunk_id} exceeds embedding request character "
                    f"limit ({max_text_characters})"
                )
            if batch and (
                len(batch) >= batch_size
                or batch_characters + chunk_characters > max_text_characters
            ):
                vectors.extend(
                    await self.embedding_repository.embed(
                        tuple(item.text for item in batch),
                        input_type="document",
                    )
                )
                batch = []
                batch_characters = 0
            batch.append(chunk)
            batch_characters += chunk_characters
        if batch:
            vectors.extend(
                await self.embedding_repository.embed(
                    tuple(item.text for item in batch),
                    input_type="document",
                )
            )
        return tuple(vectors)

    async def _upsert_chunks(
        self,
        chunks: tuple[DocumentChunk, ...],
        embeddings: tuple[tuple[float, ...], ...],
    ) -> None:
        """Persist aligned vectors with complete retrieval and citation payloads."""

        if len(chunks) != len(embeddings):
            raise RuntimeError("cannot persist unaligned chunks and embeddings")
        points = tuple(
            VectorPoint(
                point_id=chunk.chunk_id,
                dense_vector=vector,
                payload={
                    "text": chunk.text,
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.chunk_id,
                    "source_bucket": chunk.source_bucket,
                    "object_key": chunk.object_key,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "page_chunk_index": chunk.page_chunk_index,
                    "character_start": chunk.character_start,
                    "character_end": chunk.character_end,
                    "content_type": chunk.content_type,
                    "etag": chunk.etag,
                    "processing_bucket": chunk.processing_bucket,
                    "processing_object_key": chunk.processing_object_key,
                },
            )
            for chunk, vector in zip(chunks, embeddings, strict=True)
        )
        await self.vector_repository.upsert_points(points)

    async def _move_to_error_prefix(
        self,
        document: PreparedDocument,
    ) -> S3ObjectMetadata:
        """Quarantine a processing object after embedding failure.

        S3 movement is copy-then-delete. The processing copy is deleted only
        after the error-prefix copy has been created and its size verified.
        If either operation fails, the exception propagates and the durable
        processing copy is retained whenever deletion has not completed.
        """

        destination_key = error_object_key(document.source_metadata.key)
        error_metadata = await self.s3_repository.copy_object(
            document.processing_metadata.bucket,
            document.processing_metadata.key,
            document.source_metadata.bucket,
            destination_key,
            document.source_metadata.content_type,
            self._processing_user_metadata(document.source_metadata),
        )
        if error_metadata.size != document.processing_metadata.size:
            raise RuntimeError(
                "error copy size does not match processing object: "
                f"s3://{document.processing_metadata.bucket}/"
                f"{document.processing_metadata.key}"
            )
        await self.s3_repository.delete_object(
            document.processing_metadata.bucket,
            document.processing_metadata.key,
        )
        return error_metadata

    async def _release_claim(
        self,
        claim_key: str,
        suppress_errors: bool = False,
    ) -> None:
        if claim_key not in self._active_claims:
            return
        try:
            released = await self.s3_repository.release_claim(
                self.s3_settings.processing_bucket,
                claim_key,
                self._claim_owner,
            )
            if not released:
                raise RuntimeError(
                    "S3 claim was replaced or is owned by another job: "
                    f"{claim_key}"
                )
        except Exception:
            LOGGER.exception(
                "failed to release S3 claim bucket=%s claim_key=%s",
                self.s3_settings.processing_bucket,
                claim_key,
            )
            if not suppress_errors:
                raise
        else:
            self._active_claims.discard(claim_key)

    def _source_from_processing(
        self,
        original_key: str,
        processing: S3ObjectMetadata,
    ) -> S3ObjectMetadata:
        last_modified = processing.last_modified
        encoded_last_modified = processing.user_metadata.get(
            "source-last-modified"
        )
        if encoded_last_modified:
            try:
                last_modified = datetime.fromisoformat(encoded_last_modified)
            except ValueError:
                LOGGER.warning(
                    "invalid source last-modified metadata processing_key=%s",
                    processing.key,
                )
        return S3ObjectMetadata(
            bucket=self.arguments.source_bucket,
            key=original_key,
            size=processing.size,
            etag=processing.user_metadata.get("source-etag") or processing.etag,
            content_type=processing.content_type,
            last_modified=processing.last_modified,
        )

    @staticmethod
    def _processing_user_metadata(
        source: S3ObjectMetadata,
    ) -> dict[str, str]:
        metadata = {
            "source-bucket": source.bucket,
        }
        if source.etag is not None:
            metadata["source-etag"] = source.etag
        if source.last_modified is not None:
            metadata["source-last-modified"] = source.last_modified.isoformat()
        return metadata

    @staticmethod
    def _result(
        source: S3ObjectMetadata,
        processing: S3ObjectMetadata | None,
        status: Literal[
            "chunked",
            "empty",
            "unsupported",
            "failed",
            "claimed_elsewhere",
        ],
        detail: str,
        started_at: float,
        normalized_content_type: str | None = None,
        chunks: tuple[DocumentChunk, ...] = (),
        embeddings: tuple[tuple[float, ...], ...] = (),
    ) -> ObjectProcessingResult:
        return ObjectProcessingResult(
            bucket=source.bucket,
            object_key=source.key,
            processing_bucket=processing.bucket if processing else None,
            processing_object_key=processing.key if processing else None,
            status=status,
            normalized_content_type=normalized_content_type,
            chunks=chunks,
            embeddings=embeddings,
            detail=detail,
            elapsed_seconds=asyncio.get_running_loop().time() - started_at,
        )
