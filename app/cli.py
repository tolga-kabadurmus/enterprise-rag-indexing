"""Command-line parsing and startup helpers for indexing jobs."""

import argparse
import asyncio
import logging
from collections.abc import Sequence
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.jobs.base import IndexingJobArguments
from app.jobs.registry import IndexingPipelineRegistry
from app.jobs.runner import execute_job_from_factory

LOGGER = logging.getLogger(__name__)


class IndexingCommandArguments(BaseModel):
    """Pipeline selection and job-specific arguments parsed from the CLI.

    Attributes:
        pipeline: Registered pipeline name, or ``None`` when listing pipelines.
        job: Validated job arguments, or ``None`` when listing pipelines.
        list_pipelines: Whether the caller requested pipeline discovery.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str | None
    job: IndexingJobArguments | None
    list_pipelines: bool = False

    @model_validator(mode="after")
    def validate_command_state(self) -> Self:
        """Require either a complete execution command or listing command."""

        listing_state = self.pipeline is None and self.job is None
        execution_state = self.pipeline is not None and self.job is not None
        if self.list_pipelines != listing_state or not (
            listing_state or execution_state
        ):
            raise ValueError("invalid indexing command argument state")
        return self


def build_parser(pipeline_names: Sequence[str]) -> argparse.ArgumentParser:
    """Build the indexing command-line parser.

    Args:
        pipeline_names: Names accepted by the ``--pipeline`` argument.

    Returns:
        Parser for pipeline selection, bucket, key selection, and concurrency.
    """

    parser = argparse.ArgumentParser(
        description="Index documents from an S3-compatible source bucket.",
    )
    parser.add_argument(
        "--pipeline",
        choices=pipeline_names,
        help="Registered indexing pipeline to execute.",
    )
    parser.add_argument(
        "--list-pipelines",
        action="store_true",
        help="List implemented indexing pipelines and exit.",
    )
    parser.add_argument(
        "--source-bucket",
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


def parse_command_arguments(
    pipeline_names: Sequence[str],
    argv: Sequence[str] | None = None,
) -> IndexingCommandArguments:
    """Parse and validate pipeline selection and indexing arguments.

    Args:
        pipeline_names: Names that may be passed to ``--pipeline``.
        argv: Arguments without the executable name. Uses `sys.argv` when
            omitted.

    Returns:
        Pipeline selection and validated arguments for a concrete job.

    Raises:
        SystemExit: If required arguments are missing or validation fails.
    """

    parser = build_parser(pipeline_names)
    namespace = parser.parse_args(argv)
    if namespace.list_pipelines:
        if namespace.pipeline is not None:
            parser.error("--list-pipelines cannot be combined with --pipeline")
        return IndexingCommandArguments(
            pipeline=None,
            job=None,
            list_pipelines=True,
        )

    if namespace.pipeline is None:
        parser.error("--pipeline is required unless --list-pipelines is used")
    if namespace.source_bucket is None:
        parser.error("--source-bucket is required unless --list-pipelines is used")

    try:
        return IndexingCommandArguments(
            pipeline=namespace.pipeline,
            job=IndexingJobArguments(
                source_bucket=namespace.source_bucket,
                object_key=namespace.object_key,
                key_prefix=namespace.key_prefix,
                concurrency=namespace.concurrency,
            ),
        )
    except ValueError as error:
        parser.error(str(error))


def run_job_cli(
    pipeline_registry: IndexingPipelineRegistry,
    argv: Sequence[str] | None = None,
) -> int:
    """Parse arguments and execute the selected registered pipeline.

    Args:
        pipeline_registry: Implemented pipeline factories available to users.
        argv: Arguments without the executable name. Uses `sys.argv` when
            omitted.

    Returns:
        Process exit code: `0` for success, `1` for failure, or `130` when
        interrupted by the user.
    """

    command = parse_command_arguments(pipeline_registry.names, argv)
    if command.list_pipelines:
        for registration in pipeline_registry.registrations:
            print(f"{registration.name}\t{registration.description}")
        return 0

    if command.pipeline is None or command.job is None:
        raise RuntimeError("validated execution command is incomplete")

    arguments = command.job
    LOGGER.info(
        "starting indexing job pipeline=%s bucket=%s object_key=%s "
        "key_prefix=%s concurrency=%d",
        command.pipeline,
        arguments.source_bucket,
        arguments.object_key,
        arguments.key_prefix,
        arguments.concurrency,
    )

    try:
        job_factory = pipeline_registry.resolve(command.pipeline)
        asyncio.run(execute_job_from_factory(job_factory, arguments))
    except KeyboardInterrupt:
        LOGGER.warning("indexing job interrupted")
        return 130
    except Exception:
        LOGGER.exception(
            "indexing job failed pipeline=%s bucket=%s",
            command.pipeline,
            arguments.source_bucket,
        )
        return 1

    LOGGER.info(
        "indexing job completed pipeline=%s bucket=%s",
        command.pipeline,
        arguments.source_bucket,
    )
    return 0
