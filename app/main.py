"""Composition entry point for registered asynchronous indexing pipelines."""

import logging
from collections.abc import Sequence

from app.cli import run_job_cli
from app.common.settings import EmbeddingModelSettings, S3Settings
from app.common.utility.logging import configure_standard_logging
from app.document_indexers.factory import DocumentIndexerFactory
from app.jobs.base import AsyncIndexingJob, IndexingJobArguments
from app.jobs.mock import MockPDFDocumentIndexing
from app.jobs.registry import (
    IndexingPipelineRegistration,
    IndexingPipelineRegistry,
)
from app.jobs.v1 import V1IndexingPipeline
from app.repository.factory import RepositoryFactory


def build_v1_pipeline(arguments: IndexingJobArguments) -> AsyncIndexingJob:
    """Compose a v1 pipeline only when the registry selects it."""

    s3_settings = S3Settings()
    embedding_settings = EmbeddingModelSettings()
    return V1IndexingPipeline(
        arguments=arguments,
        s3_repository=RepositoryFactory.create_s3(s3_settings),
        embedding_settings=embedding_settings,
        embedding_model_repository=RepositoryFactory.create_embedding_model(
            embedding_settings
        ),
        document_indexer_factory=DocumentIndexerFactory(),
    )


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
                    "Inspect S3 objects and route PDFs to PDFChunkerV1"
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
        ``mock-pdf`` remains offline. ``v1`` loads the configured embedding
        model and inspects real S3 object metadata, but chunking and vector
        persistence are not implemented yet.
    """

    configure_standard_logging(level=logging.INFO)
    return run_job_cli(build_pipeline_registry(), argv)


if __name__ == "__main__":
    raise SystemExit(main())
