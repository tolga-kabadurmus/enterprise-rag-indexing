"""Execution helpers for asynchronous indexing jobs."""

from collections.abc import Callable

from app.jobs.base import AsyncIndexingJob, IndexingJobArguments

JobFactory = Callable[[IndexingJobArguments], AsyncIndexingJob]


async def execute_job(job: AsyncIndexingJob) -> AsyncIndexingJob:
    """Execute one job while guaranteeing its asynchronous cleanup lifecycle.

    Args:
        job: Fully composed concrete indexing job.

    Raises:
        BaseException: Propagates initialization, execution, and cleanup errors.
    """

    async with job as active_job:
        await active_job.run()
    return job


async def execute_job_from_factory(
    job_factory: JobFactory,
    arguments: IndexingJobArguments,
) -> AsyncIndexingJob:
    """Build and execute a job in the application composition layer.

    Args:
        job_factory: Callable that builds a concrete job from validated input.
        arguments: Validated source selection and concurrency settings.

    Raises:
        BaseException: Propagates job construction and execution errors.
    """

    return await execute_job(job_factory(arguments))
