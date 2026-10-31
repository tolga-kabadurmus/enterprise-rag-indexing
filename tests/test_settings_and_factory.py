import unittest
from unittest.mock import patch
from pathlib import Path

from pydantic import ValidationError

from app.common.settings.indexing import IndexingWorkspaceSettings
from app.common.settings.pdf_chunking import PDFChunkingSettings
from app.common.settings.s3 import S3Settings, StorageProvider
from app.common.settings.qdrant import QdrantSettings
from app.common.settings.vector import VectorSettings
from app.repository.s3.boto3_repository import S3Repository
from app.repository.s3.factory import StorageRepositoryFactory


class SettingsAndFactoryTests(unittest.IsolatedAsyncioTestCase):
    def test_settings_load_the_documented_environment_variable_groups(self) -> None:
        environment = {
            "S3_ENDPOINT_URL": "http://rustfs:9000",
            "S3_ACCESS_KEY": "access",
            "S3_SECRET_KEY": "secret",
            "S3_MAX_CONCURRENCY": "6",
            "S3_PROCESSING_BUCKET": "processing-custom",
            "S3_SOURCE_BUCKET": "source-documents",
            "INDEXING_WORK_DIRECTORY": "/work/custom",
            "PDF_CHUNK_SIZE": "900",
            "PDF_CHUNK_OVERLAP": "100",
            "QDRANT_COLLECTION_NAME": "custom-chunks",
            "QDRANT_BATCH_SIZE": "20",
            "VECTOR_PROVIDER": "qdrant",
        }

        with patch.dict("os.environ", environment, clear=True):
            s3_settings = S3Settings()
            workspace_settings = IndexingWorkspaceSettings()
            chunking_settings = PDFChunkingSettings()
            qdrant_settings = QdrantSettings()
            vector_settings = VectorSettings()

        self.assertEqual(s3_settings.max_concurrency, 6)
        self.assertEqual(s3_settings.processing_bucket, "processing-custom")
        self.assertEqual(s3_settings.source_bucket, "source-documents")
        self.assertEqual(workspace_settings.work_directory, Path("/work/custom"))
        self.assertEqual(chunking_settings.size, 900)
        self.assertEqual(chunking_settings.overlap, 100)
        self.assertEqual(qdrant_settings.collection_name, "custom-chunks")
        self.assertEqual(qdrant_settings.batch_size, 20)
        self.assertEqual(vector_settings.provider, "qdrant")

    def test_s3_settings_validate_provider_connection_and_concurrency(self) -> None:
        settings = S3Settings(
            endpoint_url="http://rustfs:9000",
            access_key="access",
            secret_key="secret",
            verify_tls=False,
            max_concurrency=3,
        )

        self.assertEqual(settings.provider, "rustfs")
        self.assertEqual(settings.max_concurrency, 3)
        self.assertFalse(settings.verify_tls)

    def test_s3_settings_reject_invalid_concurrency(self) -> None:
        with self.assertRaises(ValidationError):
            S3Settings(
                endpoint_url="http://rustfs:9000",
                access_key="access",
                secret_key="secret",
                max_concurrency=0,
            )

    def test_pdf_chunking_settings_reject_non_progressing_overlap(self) -> None:
        with self.assertRaises(ValidationError):
            PDFChunkingSettings(size=500, overlap=500)

    def test_workspace_settings_require_absolute_directory(self) -> None:
        with self.assertRaises(ValidationError):
            IndexingWorkspaceSettings(work_directory=Path("work/indexing"))

    async def test_factory_creates_rustfs_compatible_boto_repository(self) -> None:
        settings = S3Settings(
            endpoint_url="http://rustfs:9000",
            access_key="access",
            secret_key="secret",
        )

        factory = StorageRepositoryFactory()
        factory.register(StorageProvider.RUSTFS, S3Repository)
        repository = factory.create(settings.provider, settings)
        try:
            self.assertIsInstance(repository, S3Repository)
        finally:
            await repository.close()


if __name__ == "__main__":
    unittest.main()
