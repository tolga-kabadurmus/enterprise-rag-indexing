import asyncio
from datetime import UTC, datetime
from pathlib import Path
import tempfile
import unittest

from app.chunkers.base import DocumentChunk
from app.common.settings.embeddings import EmbeddingModelSettings
from app.common.settings.indexing import IndexingWorkspaceSettings
from app.common.settings.s3 import S3Settings
from app.common.utility.processing_keys import processing_object_key
from app.document_indexers.base import DocumentIndexingResult, LocalDocument
from app.document_indexers.factory import UnsupportedContentTypeError
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
        objects: dict[tuple[str, str], S3ObjectMetadata],
        events: list[str],
        acquire_claim: bool = True,
    ) -> None:
        self.objects = objects
        self.events = events
        self.acquire_claim = acquire_claim
        self.active_claims: set[str] = set()
        self.closed = False

    async def list_buckets(self) -> list[S3Bucket]:
        return []

    async def list_objects(
        self,
        bucket: str,
        key_prefix: str | None = None,
    ) -> list[S3ObjectMetadata]:
        self.events.append(f"list:{bucket}:{key_prefix}")
        return [
            item.model_copy(
                update={"content_type": None, "user_metadata": {}}
            )
            for (item_bucket, item_key), item in self.objects.items()
            if item_bucket == bucket
            and (key_prefix is None or item_key.startswith(key_prefix))
        ]

    async def get_object_metadata(
        self,
        bucket: str,
        object_key: str,
    ) -> S3ObjectMetadata:
        self.events.append(f"head:{bucket}:{object_key}")
        try:
            return self.objects[(bucket, object_key)]
        except KeyError as error:
            raise S3ObjectNotFoundError(bucket, object_key) from error

    async def ensure_bucket(self, bucket: str) -> None:
        self.events.append(f"ensure:{bucket}")

    async def try_acquire_claim(
        self,
        bucket: str,
        claim_key: str,
        owner: str,
        stale_after_seconds: int,
    ) -> bool:
        self.events.append(f"claim:{bucket}:{claim_key}")
        if not self.acquire_claim or claim_key in self.active_claims:
            return False
        self.active_claims.add(claim_key)
        return True

    async def release_claim(
        self,
        bucket: str,
        claim_key: str,
        owner: str,
    ) -> bool:
        self.events.append(f"release:{bucket}:{claim_key}")
        self.active_claims.discard(claim_key)
        return True

    async def copy_object(
        self,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
        content_type: str | None,
        user_metadata: dict[str, str],
    ) -> S3ObjectMetadata:
        self.events.append(
            f"copy:{source_bucket}:{source_key}:{destination_bucket}:"
            f"{destination_key}"
        )
        source = self.objects[(source_bucket, source_key)]
        copied = source.model_copy(
            update={
                "bucket": destination_bucket,
                "key": destination_key,
                "content_type": content_type,
                "user_metadata": user_metadata,
            }
        )
        self.objects[(destination_bucket, destination_key)] = copied
        return copied

    async def delete_object(self, bucket: str, object_key: str) -> None:
        self.events.append(f"delete:{bucket}:{object_key}")
        self.objects.pop((bucket, object_key), None)

    async def download_object(
        self,
        bucket: str,
        object_key: str,
        destination: Path,
    ) -> Path:
        self.events.append(f"download:{bucket}:{object_key}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"fake-pdf")
        return destination

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
        self.closed = True


class FakePDFIndexer:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def index(self, document: LocalDocument) -> DocumentIndexingResult:
        self.events.append(f"index:{document.local_path.exists()}")
        chunk = DocumentChunk(
            document_id="document-id",
            chunk_id="chunk-id",
            text="Citation-ready contract text",
            source_bucket=document.source_metadata.bucket,
            object_key=document.source_metadata.key,
            page_number=1,
            chunk_index=0,
            page_chunk_index=0,
            character_start=0,
            character_end=28,
            content_type=document.source_metadata.content_type,
            etag=document.source_metadata.etag,
            processing_bucket=document.processing_metadata.bucket,
            processing_object_key=document.processing_metadata.key,
        )
        return DocumentIndexingResult(
            source_metadata=document.source_metadata,
            processing_metadata=document.processing_metadata,
            status="chunked",
            chunks=(chunk,),
            detail="created one chunk",
        )


class FakeDocumentIndexerFactory:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def create(self, normalized_content_type: str | None):
        if normalized_content_type != "application/pdf":
            raise UnsupportedContentTypeError(
                f"unsupported content type: {normalized_content_type}"
            )
        return FakePDFIndexer(self.events)


def metadata(
    bucket: str,
    key: str,
    content_type: str | None = "application/pdf",
    user_metadata: dict[str, str] | None = None,
) -> S3ObjectMetadata:
    return S3ObjectMetadata(
        bucket=bucket,
        key=key,
        size=100,
        etag=f"etag-{key}",
        content_type=content_type,
        last_modified=datetime(2026, 1, 1, tzinfo=UTC),
        user_metadata=user_metadata or {},
    )


def build_pipeline(
    arguments: IndexingJobArguments,
    repository: FakeS3Repository,
    events: list[str],
    workspace: Path,
) -> V1IndexingPipeline:
    s3_settings = S3Settings(
        endpoint_url="http://rustfs:9000",
        access_key="access",
        secret_key="secret",
        processing_bucket="documents-processing",
    )
    return V1IndexingPipeline(
        arguments=arguments,
        s3_repository=repository,
        s3_settings=s3_settings,
        embedding_settings=EmbeddingModelSettings(
            bucket="models",
            key_prefix="embeddings",
            local_directory=Path("/models/embeddings"),
            model_file=Path("onnx/model.onnx"),
        ),
        workspace_settings=IndexingWorkspaceSettings(work_directory=workspace),
        embedding_model_repository=FakeEmbeddingModelRepository(events),
        document_indexer_factory=FakeDocumentIndexerFactory(events),
    )


class V1IndexingPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_claims_moves_downloads_and_returns_citation_chunks(self) -> None:
        events: list[str] = []
        source = metadata("documents", "contracts/a.pdf")
        repository = FakeS3Repository(
            {("documents", "contracts/a.pdf"): source},
            events,
        )
        with tempfile.TemporaryDirectory() as directory:
            pipeline = build_pipeline(
                IndexingJobArguments(
                    source_bucket="documents",
                    object_key="contracts/a.pdf",
                ),
                repository,
                events,
                Path(directory),
            )

            await execute_job(pipeline)

            self.assertEqual(pipeline.summary.chunked, 1)
            self.assertEqual(pipeline.summary.chunk_count, 1)
            self.assertEqual(
                pipeline.results[0].chunks[0].object_key,
                "contracts/a.pdf",
            )
            self.assertNotIn(("documents", "contracts/a.pdf"), repository.objects)
            processing_key = processing_object_key(
                "documents",
                "contracts/a.pdf",
            )
            self.assertIn(
                ("documents-processing", processing_key),
                repository.objects,
            )
            self.assertIn("index:True", events)
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertFalse(repository.active_claims)

        selection_index = events.index("head:documents:contracts/a.pdf")
        model_index = events.index("model-sync:models:embeddings")
        self.assertLess(selection_index, model_index)

    async def test_resumes_existing_processing_object(self) -> None:
        events: list[str] = []
        processing_key = processing_object_key("documents", "a.pdf")
        processing = metadata(
            "documents-processing",
            processing_key,
            user_metadata={"source-etag": "original-etag"},
        )
        repository = FakeS3Repository(
            {("documents-processing", processing_key): processing},
            events,
        )
        with tempfile.TemporaryDirectory() as directory:
            pipeline = build_pipeline(
                IndexingJobArguments(
                    source_bucket="documents",
                    object_key="a.pdf",
                ),
                repository,
                events,
                Path(directory),
            )

            await execute_job(pipeline)

        self.assertEqual(pipeline.summary.chunked, 1)
        self.assertEqual(pipeline.results[0].chunks[0].etag, "original-etag")
        self.assertFalse(any(event.startswith("copy:") for event in events))

    async def test_bucket_discovery_heads_processing_metadata_for_citations(self) -> None:
        events: list[str] = []
        processing_key = processing_object_key("documents", "a.pdf")
        processing = metadata(
            "documents-processing",
            processing_key,
            user_metadata={"source-etag": "original-etag"},
        )
        repository = FakeS3Repository(
            {("documents-processing", processing_key): processing},
            events,
        )
        with tempfile.TemporaryDirectory() as directory:
            pipeline = build_pipeline(
                IndexingJobArguments(source_bucket="documents"),
                repository,
                events,
                Path(directory),
            )

            await execute_job(pipeline)

        self.assertEqual(pipeline.results[0].chunks[0].etag, "original-etag")

    async def test_missing_exact_key_fails_before_model_initialization(self) -> None:
        events: list[str] = []
        repository = FakeS3Repository({}, events)
        with tempfile.TemporaryDirectory() as directory:
            pipeline = build_pipeline(
                IndexingJobArguments(
                    source_bucket="documents",
                    object_key="missing.pdf",
                ),
                repository,
                events,
                Path(directory),
            )

            with self.assertRaisesRegex(
                S3ObjectNotFoundError,
                "s3://documents/missing.pdf",
            ):
                await execute_job(pipeline)

        self.assertFalse(any(event.startswith("model-sync:") for event in events))
        self.assertEqual(events[-2:], ["model-close", "s3-close"])

    async def test_empty_selection_skips_model_initialization(self) -> None:
        events: list[str] = []
        repository = FakeS3Repository({}, events)
        with tempfile.TemporaryDirectory() as directory:
            pipeline = build_pipeline(
                IndexingJobArguments(source_bucket="documents"),
                repository,
                events,
                Path(directory),
            )

            await execute_job(pipeline)

        self.assertEqual(pipeline.summary.discovered, 0)
        self.assertFalse(any(event.startswith("model-sync:") for event in events))

    async def test_lost_claim_is_reported_without_loading_model(self) -> None:
        events: list[str] = []
        source = metadata("documents", "a.pdf")
        repository = FakeS3Repository(
            {("documents", "a.pdf"): source},
            events,
            acquire_claim=False,
        )
        with tempfile.TemporaryDirectory() as directory:
            pipeline = build_pipeline(
                IndexingJobArguments(
                    source_bucket="documents",
                    object_key="a.pdf",
                ),
                repository,
                events,
                Path(directory),
            )

            await execute_job(pipeline)

        self.assertEqual(pipeline.summary.claimed_elsewhere, 1)
        self.assertFalse(any(event.startswith("model-sync:") for event in events))


if __name__ == "__main__":
    unittest.main()
