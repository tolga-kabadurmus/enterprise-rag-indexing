"""Embedding model runtime repository contracts and implementations."""

from app.repository.embedding.base import EmbeddingModelRepository
from app.repository.embedding.onnx_repository import OnnxEmbeddingModelRepository

__all__ = ["EmbeddingModelRepository", "OnnxEmbeddingModelRepository"]
