"""Runnable mock implementation of the PDF indexing job contract.

This module intentionally performs no network or persistence operations. It is
useful for validating container wiring, command-line arguments, asynchronous
concurrency, deterministic identifiers, logging, and resource cleanup before
the real RustFS and Qdrant adapters are implemented.
"""

import asyncio
import hashlib
import logging

from pydantic import BaseModel, ConfigDict, Field

from app.jobs.base import AsyncIndexingJob, IndexingJobArguments

LOGGER = logging.getLogger(__name__)


class MockIndexedChunk(BaseModel):
    """Metadata produced for one simulated indexed chunk.

    Attributes:
        source_bucket: Requested S3-compatible source bucket.
        object_key: Exact or synthetic PDF object key processed by the mock.
        document_id: Deterministic identifier derived from bucket and key.
        chunk_id: Deterministic identifier for the simulated first chunk.
        page_number: Simulated one-based PDF page number.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_bucket: str = Field(min_length=1)
    object_key: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    page_number: int = Field(default=1, ge=1)


class MockPDFDocumentIndexing(AsyncIndexingJob):
    """Simulate a one-shot PDF indexing batch without external side effects.

    The job creates one mock candidate for the requested exact key or prefix,
    processes candidates with the configured semaphore limit, and records a
    deterministic document and chunk identifier. It does not read RustFS,
    extract a PDF, generate an embedding, or write Qdrant points.

    Args:
        arguments: Validated bucket, key selection, and concurrency settings.
    """

    def __init__(self, arguments: IndexingJobArguments) -> None:
        super().__init__(arguments)
        self.results: list[MockIndexedChunk] = []
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the mock job without opening external resources."""

        self._initialized = True
        LOGGER.warning(
            "using mock indexing pipeline; RustFS and Qdrant will not be modified"
        )

    async def run(self) -> None:
        """Process the simulated selection using bounded async concurrency.

        Raises:
            RuntimeError: If the job is run outside its async context manager.
        """

        if not self._initialized:
            raise RuntimeError("mock indexing job has not been initialized")

        object_keys = self._mock_object_keys()
        semaphore = asyncio.Semaphore(self.arguments.concurrency)
        started_at = asyncio.get_running_loop().time()

        results = await asyncio.gather(
            *(self._process_object(object_key, semaphore) for object_key in object_keys)
        )
        self.results.extend(results)

        elapsed_seconds = asyncio.get_running_loop().time() - started_at
        LOGGER.info(
            "mock indexing batch completed bucket=%s documents=%d chunks=%d "
            "failures=0 elapsed_seconds=%.3f",
            self.arguments.source_bucket,
            len(results),
            len(results),
            elapsed_seconds,
        )

    async def close(self) -> None:
        """Mark the job closed; safe to call after partial initialization."""

        self._initialized = False
        LOGGER.info("mock indexing resources closed")

    def _mock_object_keys(self) -> list[str]:
        if self.arguments.object_key is not None:
            return [self.arguments.object_key]
        if self.arguments.key_prefix is not None:
            return [f"{self.arguments.key_prefix}mock-document.pdf"]
        return ["mock-document.pdf"]

    async def _process_object(
        self,
        object_key: str,
        semaphore: asyncio.Semaphore,
    ) -> MockIndexedChunk:
        async with semaphore:
            await asyncio.sleep(0)
            document_id = self._stable_id(
                self.arguments.source_bucket,
                object_key,
            )
            chunk_id = self._stable_id(document_id, "page=1", "chunk=0")
            result = MockIndexedChunk(
                source_bucket=self.arguments.source_bucket,
                object_key=object_key,
                document_id=document_id,
                chunk_id=chunk_id,
            )
            LOGGER.info(
                "mock indexed object bucket=%s object_key=%s document_id=%s "
                "chunk_id=%s page_number=%d",
                result.source_bucket,
                result.object_key,
                result.document_id,
                result.chunk_id,
                result.page_number,
            )
            return result

    @staticmethod
    def _stable_id(*parts: str) -> str:
        value = "\0".join(parts).encode("utf-8")
        return hashlib.sha256(value).hexdigest()
