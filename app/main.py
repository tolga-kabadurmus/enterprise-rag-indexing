"""Composition entry point for registered asynchronous indexing pipelines."""

import logging
from collections.abc import Sequence

import httpx
from qdrant_client import AsyncQdrantClient

from app.cli import run_job_cli
from app.common.settings import (
    EmbeddingProvider,
    EmbeddingServiceSettings,
    IndexingWorkspaceSettings,
    PDFChunkingSettings,
    QdrantSettings,
    S3Settings,
    StorageProvider,
    VectorSettings,
    VectorProvider,
)
from app.common.utility.logging import configure_standard_logging
from app.document_indexers.factory import DocumentIndexerFactory
from app.jobs.base import AsyncIndexingJob, IndexingJobArguments
from app.jobs.mock import MockPDFDocumentIndexing
from app.jobs.registry import (
    IndexingPipelineRegistration,
    IndexingPipelineRegistry,
)
from app.jobs.v1 import V1IndexingPipeline
from app.repository.embedding_service.base import EmbeddingRepository
from app.repository.embedding_service.factory import EmbeddingRepositoryFactory
from app.repository.embedding_service.fallback_local_factory import (
    FallBackLocalEmbeddingFactory,
)
from app.repository.embedding_service.enterprise_embedding_service_repository import (
    EnterpriseEmbeddingServiceRepository,
)
from app.repository.vector.factory import VectorRepositoryFactory
from app.repository.vector.base import VectorRepositoryBase
from app.repository.vector.qdrant_repository import QdrantVectorRepository
from app.repository.s3.boto3_repository import S3Repository
from app.repository.s3.factory import StorageRepositoryFactory
from app.repository.s3.base import StorageRepositoryBase


def create_embedding_http_client(
    arguments: IndexingJobArguments,
    settings: EmbeddingServiceSettings,
) -> httpx.AsyncClient:
    """Create the job-wide HTTP client with concurrency-bounded pooling.

    The pool never exceeds either the CLI document concurrency or the
    environment-configured safety limit. The caller transfers ownership to the
    embedding repository, which closes the client during pipeline cleanup.
    """

    max_connections = min(arguments.concurrency, settings.max_connections)
    return httpx.AsyncClient(
        base_url=settings.url,
        timeout=httpx.Timeout(settings.timeout_seconds),
        limits=httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=min(
                max_connections,
                settings.max_keepalive_connections,
            ),
        ),
        verify=settings.verify_tls,
    )


def build_v1_pipeline(arguments: IndexingJobArguments) -> AsyncIndexingJob:
    """Compose a v1 pipeline only when the registry selects it."""

    s3_settings = S3Settings()
    embedding_service_settings = EmbeddingServiceSettings()
    workspace_settings = IndexingWorkspaceSettings()
    pdf_chunking_settings = PDFChunkingSettings()
    qdrant_settings = QdrantSettings()
    vector_settings = VectorSettings()
    return V1IndexingPipeline(
        arguments=arguments,
        s3_repository=create_storage_repository(s3_settings),
        s3_settings=s3_settings,
        workspace_settings=workspace_settings,
        embedding_repository=create_embedding_repository(
            arguments,
            embedding_service_settings,
        ),
        vector_repository=create_vector_repository(
            vector_settings,
            qdrant_settings,
        ),
        document_indexer_factory=DocumentIndexerFactory(
            pdf_chunking_settings=pdf_chunking_settings,
        ),
    )


def create_vector_repository(
    vector_settings: VectorSettings,
    qdrant_settings: QdrantSettings,
) -> VectorRepositoryBase:
    """Register vector providers and construct the configured implementation."""

    factory = VectorRepositoryFactory()
    factory.register(VectorProvider.QDRANT, QdrantVectorRepository)
    return factory.create(
        vector_settings.provider,
        AsyncQdrantClient(
            url=qdrant_settings.url,
            api_key=(
                qdrant_settings.api_key.get_secret_value()
                if qdrant_settings.api_key is not None
                else None
            ),
            timeout=qdrant_settings.timeout_seconds,
        ),
        qdrant_settings,
    )


def create_storage_repository(settings: S3Settings) -> StorageRepositoryBase:
    """Register storage providers and construct the configured implementation."""

    factory = StorageRepositoryFactory()
    factory.register(StorageProvider.RUSTFS, S3Repository)
    return factory.create(settings.provider, settings)


def create_embedding_repository(
    arguments: IndexingJobArguments,
    settings: EmbeddingServiceSettings,
) -> EmbeddingRepository:
    """Register embedding providers and construct the selected implementation."""

    factory = EmbeddingRepositoryFactory()
    factory.register(EmbeddingProvider.HTTPX, EnterpriseEmbeddingServiceRepository)
    factory.register(
        EmbeddingProvider.FALLBACK_LOCAL,
        FallBackLocalEmbeddingFactory,
    )
    if settings.provider is EmbeddingProvider.HTTPX:
        return factory.create(
            settings.provider,
            create_embedding_http_client(arguments, settings),
            settings,
        )
    return factory.create(settings.provider)


def build_pipeline_registry() -> IndexingPipelineRegistry:
    """Build the explicit registry of implemented indexing pipelines.

    Returns:
        Registry containing only pipelines that are currently executable.
    """

    return IndexingPipelineRegistry(
        registrations=(
            IndexingPipelineRegistration(
                name="mock-pdf",
                description=(
                    "Simulate PDF indexing without accessing RustFS or Qdrant"
                ),
                job_factory=MockPDFDocumentIndexing,
            ),
            IndexingPipelineRegistration(
                name="v1",
                description=(
                    "Claim S3 PDFs and upsert citation-ready Qdrant points"
                ),
                job_factory=build_v1_pipeline,
            ),
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Select and run one registered indexing pipeline.

    Args:
        argv: Arguments without the executable name. Uses `sys.argv` when
            omitted.

    Returns:
        Process exit code from the shared indexing CLI runner.

    Note:
        ``mock-pdf`` remains offline. ``v1`` embeds citation-ready chunks and
        idempotently upserts them to Qdrant.
    """

    configure_standard_logging(level=logging.INFO)
    s3_settings = S3Settings()
    return run_job_cli(
        build_pipeline_registry(),
        argv,
        default_source_bucket=s3_settings.source_bucket,
    )


if __name__ == "__main__":
    raise SystemExit(main())
