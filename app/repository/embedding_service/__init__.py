"""Embedding service repository contracts and HTTP implementation."""

from app.repository.embedding_service.base import EmbeddingRepository
from app.repository.embedding_service.exceptions import EmbeddingServiceRequestError
from app.repository.embedding_service.httpx_repository import (
    EmbeddingRequest,
    EmbeddingResponse,
    HttpxEmbeddingServiceRepository,
)

__all__ = [
    "EmbeddingRepository",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "EmbeddingServiceRequestError",
    "HttpxEmbeddingServiceRepository",
]
