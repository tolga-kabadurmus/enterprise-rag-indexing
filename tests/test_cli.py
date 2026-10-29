import unittest
from contextlib import redirect_stdout
from io import StringIO

from app.cli import parse_command_arguments, run_job_cli
from app.jobs.mock import MockPDFDocumentIndexing
from app.jobs.registry import IndexingPipelineRegistration, IndexingPipelineRegistry


PIPELINE_NAMES = ("mock-pdf",)


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


if __name__ == "__main__":
    unittest.main()
