import unittest
from unittest.mock import patch
from pathlib import Path

from pydantic import ValidationError

from app.common.settings.embeddings import EmbeddingModelSettings
from app.common.settings.s3 import S3Settings
from app.repository.factory import RepositoryFactory
from app.repository.embedding.onnx_repository import OnnxEmbeddingModelRepository
from app.repository.s3.boto3_repository import Boto3S3Repository


class SettingsAndFactoryTests(unittest.IsolatedAsyncioTestCase):
    def test_settings_load_the_documented_environment_variable_groups(self) -> None:
        environment = {
            "S3_ENDPOINT_URL": "http://rustfs:9000",
            "S3_ACCESS_KEY": "access",
            "S3_SECRET_KEY": "secret",
            "S3_MAX_CONCURRENCY": "6",
            "EMBEDDINGS_BUCKET": "models",
            "EMBEDDINGS_KEY_PREFIX": "embeddings",
            "EMBEDDINGS_LOCAL_DIRECTORY": "/models/embeddings",
            "EMBEDDINGS_MODEL_FILE": "onnx/model.onnx",
        }

        with patch.dict("os.environ", environment, clear=True):
            s3_settings = S3Settings()
            embedding_settings = EmbeddingModelSettings()

        self.assertEqual(s3_settings.max_concurrency, 6)
        self.assertEqual(embedding_settings.bucket, "models")
        self.assertEqual(embedding_settings.key_prefix, "embeddings")
        self.assertEqual(
            embedding_settings.local_directory,
            Path("/models/embeddings"),
        )
        self.assertEqual(
            embedding_settings.model_path,
            Path("/models/embeddings/onnx/model.onnx"),
        )

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

    def test_embedding_settings_are_configurable(self) -> None:
        settings = EmbeddingModelSettings(
            bucket="custom-models",
            key_prefix="releases/e5",
            local_directory=Path("/models/e5"),
        )

        self.assertEqual(settings.bucket, "custom-models")
        self.assertEqual(settings.key_prefix, "releases/e5")
        self.assertEqual(settings.local_directory, Path("/models/e5"))

    def test_embedding_settings_require_absolute_local_directory(self) -> None:
        with self.assertRaises(ValidationError):
            EmbeddingModelSettings(local_directory=Path("models/e5"))

    def test_embedding_settings_reject_unsafe_model_file(self) -> None:
        with self.assertRaises(ValidationError):
            EmbeddingModelSettings(model_file=Path("../model.onnx"))

    def test_factory_creates_onnx_embedding_model_repository(self) -> None:
        repository = RepositoryFactory.create_embedding_model(
            EmbeddingModelSettings()
        )

        self.assertIsInstance(repository, OnnxEmbeddingModelRepository)

    async def test_factory_creates_rustfs_compatible_boto_repository(self) -> None:
        settings = S3Settings(
            endpoint_url="http://rustfs:9000",
            access_key="access",
            secret_key="secret",
        )

        repository = RepositoryFactory.create_s3(settings)
        try:
            self.assertIsInstance(repository, Boto3S3Repository)
        finally:
            await repository.close()


if __name__ == "__main__":
    unittest.main()
