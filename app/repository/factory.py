"""Factory for infrastructure repository implementations."""

import httpx
from qdrant_client import AsyncQdrantClient

from app.common.settings.embedding_service import EmbeddingServiceSettings
from app.common.settings.s3 import S3Settings
from app.common.settings.qdrant import QdrantSettings
from app.repository.embedding_service.base import EmbeddingRepository
from app.repository.embedding_service.httpx_repository import (
    HttpxEmbeddingServiceRepository,
)
from app.repository.s3.base import S3Repository
from app.repository.s3.boto3_repository import Boto3S3Repository
from app.repository.qdrant.async_repository import AsyncQdrantRepository
from app.repository.qdrant.base import QdrantRepository


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
    def create_embedding_service(
        settings: EmbeddingServiceSettings,
        httpx_client: httpx.AsyncClient,
    ) -> EmbeddingRepository:
        """Create the configured embedding provider.

        The default and currently supported provider is HTTPX. The client is
        deliberately supplied by application startup so its connection pool
        can be shared by all concurrently processed documents.
        """

        if settings.provider == "httpx":
            return HttpxEmbeddingServiceRepository(httpx_client, settings)
        raise ValueError(
            "unsupported embedding service provider: "
            f"{settings.provider}"
        )

    @staticmethod
    def create_qdrant(
        settings: QdrantSettings,
        client: AsyncQdrantClient,
    ) -> QdrantRepository:
        """Create the asynchronous Qdrant persistence adapter."""

        return AsyncQdrantRepository(client, settings)
