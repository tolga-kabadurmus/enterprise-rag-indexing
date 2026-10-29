import unittest

from app.jobs.base import IndexingJobArguments
from app.jobs.mock import MockPDFDocumentIndexing
from app.jobs.runner import execute_job


class MockPDFDocumentIndexingTests(unittest.IsolatedAsyncioTestCase):
    async def test_indexes_exact_key_with_deterministic_ids(self) -> None:
        arguments = IndexingJobArguments(
            source_bucket="documents",
            object_key="contracts/contract.pdf",
        )
        first_job = MockPDFDocumentIndexing(arguments)
        second_job = MockPDFDocumentIndexing(arguments)

        await execute_job(first_job)
        await execute_job(second_job)

        self.assertEqual(first_job.results, second_job.results)
        self.assertEqual(first_job.results[0].object_key, "contracts/contract.pdf")
        self.assertEqual(first_job.results[0].page_number, 1)

    async def test_prefix_creates_an_explicit_mock_candidate(self) -> None:
        job = MockPDFDocumentIndexing(
            IndexingJobArguments(
                source_bucket="documents",
                key_prefix="contracts/2026/",
                concurrency=4,
            )
        )

        await execute_job(job)

        self.assertEqual(len(job.results), 1)
        self.assertEqual(
            job.results[0].object_key,
            "contracts/2026/mock-document.pdf",
        )


if __name__ == "__main__":
    unittest.main()
