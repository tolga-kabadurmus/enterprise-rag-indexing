"""Factory for infrastructure repository implementations."""

from app.common.settings.embeddings import EmbeddingModelSettings
from app.common.settings.s3 import S3Settings
from app.repository.embedding.base import EmbeddingModelRepository
from app.repository.embedding.onnx_repository import OnnxEmbeddingModelRepository
from app.repository.s3.base import S3Repository
from app.repository.s3.boto3_repository import Boto3S3Repository


class RepositoryFactory:
    """Create provider-specific infrastructure adapters from settings."""

    @staticmethod
    def create_s3(settings: S3Settings) -> S3Repository:
        """Create the configured S3-compatible repository.

        Args:
            settings: Validated S3 provider and connection settings.

        Returns:
            A RustFS-compatible boto3 repository.
        """

        if settings.provider == "rustfs":
            return Boto3S3Repository(settings)
        raise ValueError(f"unsupported S3 provider: {settings.provider}")

    @staticmethod
    def create_embedding_model(
        settings: EmbeddingModelSettings,
    ) -> EmbeddingModelRepository:
        """Create the configured local embedding model runtime adapter."""

        if settings.runtime == "onnx":
            return OnnxEmbeddingModelRepository()
        raise ValueError(
            f"unsupported embedding model runtime: {settings.runtime}"
        )
