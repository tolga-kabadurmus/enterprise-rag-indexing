"""Command-line parsing and startup helpers for indexing jobs."""

import argparse
import asyncio
import logging
from collections.abc import Sequence

from app.jobs.base import IndexingJobArguments
from app.jobs.runner import JobFactory, execute_job_from_factory

LOGGER = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the indexing command-line parser.

    Returns:
        Parser for bucket, key selection, and concurrency arguments.
    """

    parser = argparse.ArgumentParser(
        description="Index documents from an S3-compatible source bucket.",
    )
    parser.add_argument(
        "--source-bucket",
        required=True,
        help="S3 bucket containing the source documents.",
    )

    selector = parser.add_mutually_exclusive_group()
    selector.add_argument(
        "--object-key",
        help="Index exactly one S3 object key.",
    )
    selector.add_argument(
        "--key-prefix",
        help="Index eligible objects whose keys start with this prefix.",
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Maximum number of documents processed concurrently (default: 4).",
    )
    return parser


def parse_job_arguments(argv: Sequence[str] | None = None) -> IndexingJobArguments:
    """Parse and validate indexing arguments.

    Args:
        argv: Arguments without the executable name. Uses `sys.argv` when
            omitted.

    Returns:
        Validated arguments for a concrete indexing job.

    Raises:
        SystemExit: If required arguments are missing or validation fails.
    """

    parser = build_parser()
    namespace = parser.parse_args(argv)
    try:
        return IndexingJobArguments(
            source_bucket=namespace.source_bucket,
            object_key=namespace.object_key,
            key_prefix=namespace.key_prefix,
            concurrency=namespace.concurrency,
        )
    except ValueError as error:
        parser.error(str(error))


def run_job_cli(
    job_factory: JobFactory,
    argv: Sequence[str] | None = None,
) -> int:
    """Parse arguments and execute a concrete job factory.

    Args:
        job_factory: Composition-layer callable that constructs the selected
            concrete indexing job.
        argv: Arguments without the executable name. Uses `sys.argv` when
            omitted.

    Returns:
        Process exit code: `0` for success, `1` for failure, or `130` when
        interrupted by the user.
    """

    arguments = parse_job_arguments(argv)
    LOGGER.info(
        "starting indexing job bucket=%s object_key=%s key_prefix=%s concurrency=%d",
        arguments.source_bucket,
        arguments.object_key,
        arguments.key_prefix,
        arguments.concurrency,
    )

    try:
        asyncio.run(execute_job_from_factory(job_factory, arguments))
    except KeyboardInterrupt:
        LOGGER.warning("indexing job interrupted")
        return 130
    except Exception:
        LOGGER.exception("indexing job failed bucket=%s", arguments.source_bucket)
        return 1

    LOGGER.info("indexing job completed bucket=%s", arguments.source_bucket)
    return 0
