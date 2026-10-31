import unittest

from app.jobs.base import AsyncIndexingJob, IndexingJobArguments
from app.jobs.runner import execute_job


class RecordingJob(AsyncIndexingJob):
    def __init__(
        self,
        arguments: IndexingJobArguments,
        *,
        fail_initialize: bool = False,
        fail_run: bool = False,
    ) -> None:
        super().__init__(arguments)
        self.events: list[str] = []
        self.fail_initialize = fail_initialize
        self.fail_run = fail_run

    async def initialize(self) -> None:
        self.events.append("initialize")
        if self.fail_initialize:
            raise RuntimeError("initialization failed")

    async def run(self) -> None:
        self.events.append("run")
        if self.fail_run:
            raise RuntimeError("run failed")

    async def close(self) -> None:
        self.events.append("close")


class ExecuteJobTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.arguments = IndexingJobArguments(source_bucket="documents")

    async def test_executes_complete_lifecycle(self) -> None:
        job = RecordingJob(self.arguments)

        await execute_job(job)

        self.assertEqual(job.events, ["initialize", "run", "close"])

    async def test_closes_after_run_failure(self) -> None:
        job = RecordingJob(self.arguments, fail_run=True)

        with self.assertRaisesRegex(RuntimeError, "run failed"):
            await execute_job(job)

        self.assertEqual(job.events, ["initialize", "run", "close"])

    async def test_closes_after_initialization_failure(self) -> None:
        job = RecordingJob(self.arguments, fail_initialize=True)

        with self.assertRaisesRegex(RuntimeError, "initialization failed"):
            await execute_job(job)

        self.assertEqual(job.events, ["initialize", "close"])


if __name__ == "__main__":
    unittest.main()
