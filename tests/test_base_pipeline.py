import unittest
from pathlib import Path
from typing import Literal

from app.jobs.base import IndexingJobArguments
from app.jobs.runner import execute_job
from app.pipelines.base import BasePipeline
from app.repository.embedding_service.base import (
    EmbeddingRepository,
    EmbeddingVector,
    SparseEmbedding,
)
from app.repository.models import S3Bucket, S3ObjectMetadata
from app.repository.s3.base import StorageRepositoryBase
from app.repository.vector.base import VectorPoint, VectorRepositoryBase


class RecordingVectorRepository(VectorRepositoryBase):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def ensure_collection(self) -> None:
        self.events.append("qdrant-ensure")

    async def upsert_points(self, points: tuple[VectorPoint, ...]) -> None:
        self.events.append(f"qdrant-upsert:{len(points)}")

    async def close(self) -> None:
        self.events.append("qdrant-close")


class RecordingEmbeddingRepository(EmbeddingRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    @property
    def max_batch_size(self) -> int:
        return 32

    @property
    def max_text_characters(self) -> int:
        return 32_000

    async def embed(
        self,
        texts: tuple[str, ...],
        input_type: Literal["document", "query"] = "document",
    ) -> tuple[EmbeddingVector, ...]:
        return tuple(
            EmbeddingVector(
                dense=(1.0,),
                sparse=SparseEmbedding(indices=(1,), values=(1.0,)),
            )
            for _ in texts
        )

    async def close(self) -> None:
        self.events.append("embedding-close")


class RecordingS3Repository(StorageRepositoryBase):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def list_buckets(self) -> list[S3Bucket]:
        return []

    async def list_objects(self, bucket: str, key_prefix: str | None = None) -> list[S3ObjectMetadata]:
        return []

    async def get_object_metadata(self, bucket: str, object_key: str) -> S3ObjectMetadata:
        raise NotImplementedError

    async def ensure_bucket(self, bucket: str) -> None:
        raise NotImplementedError

    async def try_acquire_claim(self, bucket: str, claim_key: str, owner: str, stale_after_seconds: int) -> bool:
        raise NotImplementedError

    async def release_claim(self, bucket: str, claim_key: str, owner: str) -> bool:
        raise NotImplementedError

    async def copy_object(self, source_bucket: str, source_key: str, destination_bucket: str, destination_key: str, content_type: str | None, user_metadata: dict[str, str]) -> S3ObjectMetadata:
        raise NotImplementedError

    async def delete_object(self, bucket: str, object_key: str) -> None:
        raise NotImplementedError

    async def download_object(self, bucket: str, object_key: str, destination: Path) -> Path:
        raise NotImplementedError

    async def download_prefix(self, bucket: str, key_prefix: str, destination_directory: Path) -> list[Path]:
        raise AssertionError("indexing must not download model artifacts")

    async def close(self) -> None:
        self.events.append("s3-close")


class RecordingPipeline(BasePipeline):
    def __init__(self, events: list[str], fail: bool = False) -> None:
        super().__init__(
            IndexingJobArguments(source_bucket="documents"),
            RecordingS3Repository(events),
            RecordingEmbeddingRepository(events),
            RecordingVectorRepository(events),
        )
        self.events = events
        self.fail = fail

    async def run(self) -> None:
        self.events.append("run")
        if self.fail:
            raise RuntimeError("indexing failed")

    async def close_pipeline_resources(self) -> None:
        self.events.append("pipeline-close")


class BasePipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_closes_embedding_http_repository_after_success(self) -> None:
        events: list[str] = []
        await execute_job(RecordingPipeline(events))
        self.assertEqual(events, ["qdrant-ensure", "run", "pipeline-close", "qdrant-close", "embedding-close", "s3-close"])

    async def test_closes_embedding_http_repository_after_failure(self) -> None:
        events: list[str] = []
        with self.assertRaisesRegex(RuntimeError, "indexing failed"):
            await execute_job(RecordingPipeline(events, fail=True))
        self.assertEqual(events, ["qdrant-ensure", "run", "pipeline-close", "qdrant-close", "embedding-close", "s3-close"])


if __name__ == "__main__":
    unittest.main()
