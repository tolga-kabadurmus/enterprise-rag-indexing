import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from app.cli import parse_command_arguments, run_job_cli
from app.jobs.mock import MockPDFDocumentIndexing
from app.jobs.base import AsyncIndexingJob, IndexingJobArguments
from app.jobs.registry import IndexingPipelineRegistration, IndexingPipelineRegistry
from app.repository.exceptions import S3ObjectNotFoundError


PIPELINE_NAMES = ("mock-pdf",)


class FailedObjectJob(AsyncIndexingJob):
    """Test job that completes its batch with one isolated object failure."""

    @property
    def failed_count(self) -> int:
        return 1

    async def run(self) -> None:
        return None


class ParseCommandArgumentsTests(unittest.TestCase):
    def test_parses_exact_object_key(self) -> None:
        command = parse_command_arguments(
            PIPELINE_NAMES,
            [
                "--pipeline",
                "mock-pdf",
                "--source-bucket",
                "documents",
                "--object-key",
                "contracts/contract.pdf",
                "--concurrency",
                "2",
            ]
        )
        arguments = command.job

        self.assertEqual(command.pipeline, "mock-pdf")
        self.assertIsNotNone(arguments)
        assert arguments is not None
        self.assertEqual(arguments.source_bucket, "documents")
        self.assertEqual(arguments.object_key, "contracts/contract.pdf")
        self.assertIsNone(arguments.key_prefix)
        self.assertEqual(arguments.concurrency, 2)

    def test_parses_key_prefix(self) -> None:
        command = parse_command_arguments(
            PIPELINE_NAMES,
            [
                "--pipeline",
                "mock-pdf",
                "--source-bucket",
                "documents",
                "--key-prefix",
                "contracts/",
            ],
        )
        arguments = command.job

        self.assertIsNotNone(arguments)
        assert arguments is not None
        self.assertEqual(arguments.key_prefix, "contracts/")
        self.assertIsNone(arguments.object_key)

    def test_rejects_object_key_and_prefix_together(self) -> None:
        with self.assertRaises(SystemExit):
            parse_command_arguments(
                PIPELINE_NAMES,
                [
                    "--pipeline",
                    "mock-pdf",
                    "--source-bucket",
                    "documents",
                    "--object-key",
                    "contract.pdf",
                    "--key-prefix",
                    "contracts/",
                ]
            )

    def test_rejects_zero_concurrency(self) -> None:
        with self.assertRaises(SystemExit):
            parse_command_arguments(
                PIPELINE_NAMES,
                [
                    "--pipeline",
                    "mock-pdf",
                    "--source-bucket",
                    "documents",
                    "--concurrency",
                    "0",
                ],
            )

    def test_rejects_missing_pipeline(self) -> None:
        with self.assertRaises(SystemExit):
            parse_command_arguments(
                PIPELINE_NAMES,
                ["--source-bucket", "documents"],
            )

    def test_rejects_unknown_pipeline(self) -> None:
        with self.assertRaises(SystemExit):
            parse_command_arguments(
                PIPELINE_NAMES,
                [
                    "--pipeline",
                    "unknown",
                    "--source-bucket",
                    "documents",
                ],
            )

    def test_lists_registered_pipelines_without_job_arguments(self) -> None:
        registry = IndexingPipelineRegistry(
            registrations=(
                IndexingPipelineRegistration(
                    name="mock-pdf",
                    description="Mock PDF pipeline",
                    job_factory=MockPDFDocumentIndexing,
                ),
            )
        )
        output = StringIO()

        with redirect_stdout(output):
            exit_code = run_job_cli(registry, ["--list-pipelines"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(output.getvalue(), "mock-pdf\tMock PDF pipeline\n")

    def test_missing_exact_object_logs_concise_error_and_returns_one(self) -> None:
        def missing_object_factory(arguments):
            raise S3ObjectNotFoundError(
                arguments.source_bucket,
                arguments.object_key or "unexpected",
            )

        registry = IndexingPipelineRegistry(
            registrations=(
                IndexingPipelineRegistration(
                    name="v1",
                    description="V1 pipeline",
                    job_factory=missing_object_factory,
                ),
            )
        )

        with patch("app.cli.LOGGER.error") as log_error:
            exit_code = run_job_cli(
                registry,
                [
                    "--pipeline",
                    "v1",
                    "--source-bucket",
                    "documents",
                    "--object-key",
                    "contracts/missing.pdf",
                ],
            )

        self.assertEqual(exit_code, 1)
        log_error.assert_called_once()
        self.assertNotIn("exc_info", log_error.call_args.kwargs)
        self.assertIn(
            "Source object not found: s3://documents/contracts/missing.pdf",
            str(log_error.call_args.args[-1]),
        )

    def test_uses_configured_source_bucket_when_argument_is_omitted(self) -> None:
        command = parse_command_arguments(
            PIPELINE_NAMES,
            ["--pipeline", "mock-pdf"],
            default_source_bucket="configured-documents",
        )

        self.assertIsNotNone(command.job)
        assert command.job is not None
        self.assertEqual(command.job.source_bucket, "configured-documents")

    def test_returns_one_when_batch_contains_failed_object(self) -> None:
        registry = IndexingPipelineRegistry(
            registrations=(
                IndexingPipelineRegistration(
                    name="v1",
                    description="V1 pipeline",
                    job_factory=FailedObjectJob,
                ),
            )
        )

        with patch("app.cli.LOGGER.error") as log_error:
            exit_code = run_job_cli(
                registry,
                [
                    "--pipeline",
                    "v1",
                    "--source-bucket",
                    "documents",
                ],
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(log_error.call_args.args[-1], 1)


if __name__ == "__main__":
    unittest.main()
