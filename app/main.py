"""Composition entry point for registered asynchronous indexing pipelines."""

import logging
from collections.abc import Sequence

from app.cli import run_job_cli
from app.jobs.mock import MockPDFDocumentIndexing
from app.jobs.registry import (
    IndexingPipelineRegistration,
    IndexingPipelineRegistry,
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
        The current registry contains only ``mock-pdf``. Future pipelines are
        made available by explicitly registering their job factories here.
    """

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return run_job_cli(build_pipeline_registry(), argv)


if __name__ == "__main__":
    raise SystemExit(main())
