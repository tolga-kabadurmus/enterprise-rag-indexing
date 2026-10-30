import asyncio
from pathlib import Path
import unittest

from app.common.settings.embeddings import EmbeddingModelSettings
from app.document_indexers.factory import DocumentIndexerFactory
from app.jobs.base import IndexingJobArguments
from app.jobs.runner import execute_job
from app.jobs.v1 import V1IndexingPipeline
from app.repository.embedding.base import EmbeddingModelRepository
from app.repository.exceptions import S3ObjectNotFoundError
from app.repository.models import S3Bucket, S3ObjectMetadata
from app.repository.s3.base import S3Repository


class FakeEmbeddingModelRepository(EmbeddingModelRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    async def load(self, model_path: Path) -> None:
        self.events.append(f"model-load:{model_path}")
        self._loaded = True

    async def close(self) -> None:
        self.events.append("model-close")
        self._loaded = False


class FakeS3Repository(S3Repository):
    def __init__(
        self,
        listed: list[S3ObjectMetadata],
        headed: dict[str, S3ObjectMetadata | Exception],
        events: list[str],
    ) -> None:
        self.listed = listed
        self.headed = headed
        self.events = events
        self.list_calls: list[tuple[str, str | None]] = []
        self.head_calls: list[tuple[str, str]] = []
        self.active_heads = 0
        self.maximum_active_heads = 0

    async def list_buckets(self) -> list[S3Bucket]:
        return []

    async def list_objects(
        self,
        bucket: str,
        key_prefix: str | None = None,
    ) -> list[S3ObjectMetadata]:
        self.events.append(f"list:{bucket}:{key_prefix}")
        self.list_calls.append((bucket, key_prefix))
        return self.listed

    async def get_object_metadata(
        self,
        bucket: str,
        object_key: str,
    ) -> S3ObjectMetadata:
        self.events.append(f"head:{bucket}:{object_key}")
        self.head_calls.append((bucket, object_key))
        self.active_heads += 1
        self.maximum_active_heads = max(
            self.maximum_active_heads,
            self.active_heads,
        )
        try:
            await asyncio.sleep(0)
            result = self.headed[object_key]
            if isinstance(result, Exception):
                raise result
            return result
        finally:
            self.active_heads -= 1

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
        self.events.append(f"model-sync:{bucket}:{key_prefix}")
        return [destination_directory / "onnx/model.onnx"]

    async def close(self) -> None:
        self.events.append("s3-close")


def metadata(
    key: str,
    content_type: str | None = None,
) -> S3ObjectMetadata:
    return S3ObjectMetadata(
        bucket="documents",
        key=key,
        size=100,
        etag=f"etag-{key}",
        content_type=content_type,
    )


def build_pipeline(
    arguments: IndexingJobArguments,
    repository: FakeS3Repository,
    events: list[str],
) -> V1IndexingPipeline:
    return V1IndexingPipeline(
        arguments=arguments,
        s3_repository=repository,
        embedding_settings=EmbeddingModelSettings(
            bucket="models",
            key_prefix="embeddings",
            local_directory=Path("/models/embeddings"),
            model_file=Path("onnx/model.onnx"),
        ),
        embedding_model_repository=FakeEmbeddingModelRepository(events),
        document_indexer_factory=DocumentIndexerFactory(),
    )


class V1IndexingPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_key_uses_head_without_listing(self) -> None:
        events: list[str] = []
        complete_metadata = metadata("contracts/a.pdf", "application/pdf")
        repository = FakeS3Repository(
            listed=[],
            headed={"contracts/a.pdf": complete_metadata},
            events=events,
        )
        pipeline = build_pipeline(
            IndexingJobArguments(
                source_bucket="documents",
                object_key="contracts/a.pdf",
            ),
            repository,
            events,
        )

        await execute_job(pipeline)

        self.assertEqual(repository.list_calls, [])
        self.assertEqual(
            repository.head_calls,
            [("documents", "contracts/a.pdf")],
        )
        self.assertIsNotNone(pipeline.summary)
        assert pipeline.summary is not None
        self.assertEqual(pipeline.summary.discovered, 1)
        self.assertEqual(pipeline.summary.not_implemented, 1)
        self.assertEqual(
            events,
            [
                "head:documents:contracts/a.pdf",
                "model-sync:models:embeddings",
                "model-load:/models/embeddings/onnx/model.onnx",
                "model-close",
                "s3-close",
            ],
        )

    async def test_lists_prefix_and_isolates_unsupported_and_failed_objects(self) -> None:
        events: list[str] = []
        discovered = [
            metadata("contracts/a.pdf"),
            metadata("contracts/readme.txt"),
            metadata("contracts/broken.pdf"),
        ]
        repository = FakeS3Repository(
            listed=discovered,
            headed={
                "contracts/a.pdf": metadata(
                    "contracts/a.pdf",
                    "application/pdf; charset=binary",
                ),
                "contracts/readme.txt": metadata(
                    "contracts/readme.txt",
                    "text/plain",
                ),
                "contracts/broken.pdf": S3ObjectNotFoundError(
                    "documents",
                    "contracts/broken.pdf",
                ),
            },
            events=events,
        )
        pipeline = build_pipeline(
            IndexingJobArguments(
                source_bucket="documents",
                key_prefix="contracts/",
                concurrency=2,
            ),
            repository,
            events,
        )

        await execute_job(pipeline)

        self.assertEqual(repository.list_calls, [("documents", "contracts/")])
        self.assertLessEqual(repository.maximum_active_heads, 2)
        self.assertGreaterEqual(repository.maximum_active_heads, 2)
        self.assertIsNotNone(pipeline.summary)
        assert pipeline.summary is not None
        self.assertEqual(pipeline.summary.discovered, 3)
        self.assertEqual(pipeline.summary.processed, 2)
        self.assertEqual(pipeline.summary.not_implemented, 1)
        self.assertEqual(pipeline.summary.unsupported, 1)
        self.assertEqual(pipeline.summary.failed, 1)

    async def test_missing_exact_key_fails_job_and_still_closes_resources(self) -> None:
        events: list[str] = []
        repository = FakeS3Repository(
            listed=[],
            headed={
                "missing.pdf": S3ObjectNotFoundError(
                    "documents",
                    "missing.pdf",
                )
            },
            events=events,
        )
        pipeline = build_pipeline(
            IndexingJobArguments(
                source_bucket="documents",
                object_key="missing.pdf",
            ),
            repository,
            events,
        )

        with self.assertRaisesRegex(
            S3ObjectNotFoundError,
            "s3://documents/missing.pdf",
        ):
            await execute_job(pipeline)

        self.assertEqual(
            events,
            [
                "head:documents:missing.pdf",
                "model-close",
                "s3-close",
            ],
        )

    async def test_empty_selection_skips_model_initialization(self) -> None:
        events: list[str] = []
        repository = FakeS3Repository(
            listed=[],
            headed={},
            events=events,
        )
        pipeline = build_pipeline(
            IndexingJobArguments(source_bucket="documents"),
            repository,
            events,
        )

        await execute_job(pipeline)

        self.assertIsNotNone(pipeline.summary)
        assert pipeline.summary is not None
        self.assertEqual(pipeline.summary.discovered, 0)
        self.assertEqual(pipeline.summary.processed, 0)
        self.assertEqual(
            events,
            [
                "list:documents:None",
                "model-close",
                "s3-close",
            ],
        )


if __name__ == "__main__":
    unittest.main()
