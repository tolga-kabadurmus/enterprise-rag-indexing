import unittest
from pathlib import Path

from app.common.settings.embeddings import EmbeddingModelSettings
from app.jobs.base import IndexingJobArguments
from app.jobs.runner import execute_job
from app.pipelines.base import BasePipeline
from app.repository.models import S3Bucket, S3ObjectMetadata
from app.repository.s3.base import S3Repository


class RecordingS3Repository(S3Repository):
    def __init__(self, events: list[str], files: list[Path]) -> None:
        self.events = events
        self.files = files

    async def list_buckets(self) -> list[S3Bucket]:
        return []

    async def list_objects(
        self,
        bucket: str,
        key_prefix: str | None = None,
    ) -> list[S3ObjectMetadata]:
        return []

    async def get_object_metadata(
        self,
        bucket: str,
        object_key: str,
    ) -> S3ObjectMetadata:
        raise NotImplementedError

    async def ensure_bucket(self, bucket: str) -> None:
        raise NotImplementedError

    async def try_acquire_claim(
        self,
        bucket: str,
        claim_key: str,
        owner: str,
        stale_after_seconds: int,
    ) -> bool:
        raise NotImplementedError

    async def release_claim(
        self,
        bucket: str,
        claim_key: str,
        owner: str,
    ) -> bool:
        raise NotImplementedError

    async def copy_object(
        self,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
        content_type: str | None,
        user_metadata: dict[str, str],
    ) -> S3ObjectMetadata:
        raise NotImplementedError

    async def delete_object(self, bucket: str, object_key: str) -> None:
        raise NotImplementedError

    async def download_object(
        self,
        bucket: str,
        object_key: str,
        destination: Path,
    ) -> Path:
        raise NotImplementedError

    async def download_prefix(
        self,
        bucket: str,
        key_prefix: str,
        destination_directory: Path,
    ) -> list[Path]:
        self.events.append(
            f"download:{bucket}:{key_prefix}:{destination_directory}"
        )
        return self.files

    async def close(self) -> None:
        self.events.append("repository-close")


class RecordingPipeline(BasePipeline):
    def __init__(self, repository: RecordingS3Repository, events: list[str]) -> None:
        super().__init__(
            IndexingJobArguments(source_bucket="documents"),
            repository,
            EmbeddingModelSettings(
                bucket="models",
                key_prefix="embeddings",
                local_directory=Path("/models/embeddings"),
            ),
        )
        self.events = events

    async def initialize_pipeline_resources(self) -> None:
        self.events.append("pipeline-initialize")

    async def run(self) -> None:
        self.events.append("run")

    async def close_pipeline_resources(self) -> None:
        self.events.append("pipeline-close")


class BasePipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_downloads_embedding_model_before_pipeline_initialization(self) -> None:
        events: list[str] = []
        repository = RecordingS3Repository(
            events,
            [Path("/models/embeddings/config.json")],
        )
        pipeline = RecordingPipeline(repository, events)

        await execute_job(pipeline)

        self.assertEqual(
            events,
            [
                "download:models:embeddings:/models/embeddings",
                "pipeline-initialize",
                "run",
                "pipeline-close",
                "repository-close",
            ],
        )

    async def test_empty_embedding_prefix_fails_and_closes_repository(self) -> None:
        events: list[str] = []
        repository = RecordingS3Repository(events, [])
        pipeline = RecordingPipeline(repository, events)

        with self.assertRaisesRegex(RuntimeError, "contains no downloadable files"):
            await execute_job(pipeline)

        self.assertEqual(
            events,
            [
                "download:models:embeddings:/models/embeddings",
                "pipeline-close",
                "repository-close",
            ],
        )


if __name__ == "__main__":
    unittest.main()
