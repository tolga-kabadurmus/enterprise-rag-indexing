import unittest

from app.jobs.mock import MockPDFDocumentIndexing
from app.jobs.registry import IndexingPipelineRegistration, IndexingPipelineRegistry
from app.main import build_pipeline_registry


class IndexingPipelineRegistryTests(unittest.TestCase):
    def test_application_registers_mock_and_v1_workflow_version(self) -> None:
        registry = build_pipeline_registry()

        self.assertEqual(registry.names, ("mock-pdf", "v1"))

    def test_resolves_registered_job_factory(self) -> None:
        registry = IndexingPipelineRegistry(
            registrations=(
                IndexingPipelineRegistration(
                    name="mock-pdf",
                    description="Mock PDF pipeline",
                    job_factory=MockPDFDocumentIndexing,
                ),
            )
        )

        self.assertIs(registry.resolve("mock-pdf"), MockPDFDocumentIndexing)

    def test_rejects_duplicate_pipeline_name(self) -> None:
        registration = IndexingPipelineRegistration(
            name="mock-pdf",
            description="Mock PDF pipeline",
            job_factory=MockPDFDocumentIndexing,
        )

        with self.assertRaisesRegex(ValueError, "already registered"):
            IndexingPipelineRegistry(
                registrations=(registration, registration),
            )

    def test_rejects_unknown_pipeline_name(self) -> None:
        registry = IndexingPipelineRegistry(
            registrations=(
                IndexingPipelineRegistration(
                    name="mock-pdf",
                    description="Mock PDF pipeline",
                    job_factory=MockPDFDocumentIndexing,
                ),
            )
        )

        with self.assertRaisesRegex(KeyError, "unknown indexing pipeline"):
            registry.resolve("pdf")


if __name__ == "__main__":
    unittest.main()
