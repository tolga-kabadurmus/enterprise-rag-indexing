"""Embedding repository contract, factory, and implementations."""

from app.repository.embedding_service.base import (
    EmbeddingRepository,
    EmbeddingVector,
    SparseEmbedding,
)
from app.repository.embedding_service.exceptions import EmbeddingServiceRequestError
from app.repository.embedding_service.factory import EmbeddingRepositoryFactory
from app.repository.embedding_service.fallback_local_factory import (
    FallBackLocalEmbeddingFactory,
)
from app.repository.embedding_service.enterprise_embedding_service_repository import (
    EmbeddingRequest,
    EmbeddingResponse,
    EnterpriseEmbeddingServiceRepository,
)

__all__ = [
    "EmbeddingRepository",
    "EmbeddingRepositoryFactory",
    "EmbeddingVector",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "EmbeddingServiceRequestError",
    "FallBackLocalEmbeddingFactory",
    "SparseEmbedding",
    "EnterpriseEmbeddingServiceRepository",
]
