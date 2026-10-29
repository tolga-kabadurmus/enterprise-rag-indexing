# Asynchronous jobs

## Lifecycle

Every concrete indexing job inherits `AsyncIndexingJob` and follows this
sequence:

```text
construct -> initialize -> run once -> close -> exit
                |             |
                +-- failure --+--> close -> propagate error
```

The runner always uses an asynchronous context manager:

```python
from app.jobs.runner import execute_job

await execute_job(job)
```

This is equivalent to the required application pattern:

```python
async with job as active_job:
    await active_job.run()
```

## Implementing a job

```python
from app.jobs.base import AsyncIndexingJob


class PDFDocumentIndexing(AsyncIndexingJob):
    async def initialize(self) -> None:
        # Open injected repositories or provider clients.
        ...

    async def run(self) -> None:
        # Execute exactly one requested indexing batch.
        ...

    async def close(self) -> None:
        # Safely close every resource that was successfully opened.
        ...
```

`close` must be idempotent and must tolerate partial initialization. The base
class calls it when initialization fails as well as when `run` succeeds or
raises.

## Concurrency

The `concurrency` argument is a limit, not a requested task count. A concrete
job should create an `asyncio.Semaphore` and process discovered documents with
`asyncio.gather`. Blocking SDK or CPU work, including `boto3`, PDF rendering and
OCR, must run through a bounded thread or process boundary so it does not block
the event loop.

The job remains responsible for per-document success and failure reporting.
One failed document should not corrupt the state of other documents in the
same batch.
