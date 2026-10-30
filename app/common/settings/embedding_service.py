"""Validated settings for the shared embedding HTTP service."""

from enum import Enum

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingProvider(str, Enum):
    """Supported embedding repository provider keys."""

    HTTPX = "httpx"
    FALLBACK_LOCAL = "fallback_local"


class EmbeddingServiceSettings(BaseSettings):
    """Connection and response-validation settings for embedding requests.

    Values are read from variables prefixed with ``EMBEDDING_SERVICE_``.
    """

    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_SERVICE_",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    url: str = Field(
        default="http://enterprise-rag-embedding-service:8081",
        min_length=1,
    )
    api_path: str = Field(default="/v1/embeddings", min_length=1)
    provider: EmbeddingProvider = EmbeddingProvider.HTTPX
    timeout_seconds: float = Field(default=60.0, gt=0)
    verify_tls: bool = True
    max_connections: int = Field(default=4, ge=1)
    max_keepalive_connections: int = Field(default=4, ge=0)
    max_batch_size: int = Field(default=32, ge=1)
    max_text_characters: int = Field(default=32_000, ge=1)
    expected_model: str = Field(
        default="intfloat/multilingual-e5-small",
        min_length=1,
    )
    expected_dimension: int = Field(default=384, ge=1)
    expected_sparse_model: str = Field(
        default="multilingual-e5-token-frequency-v1",
        min_length=1,
    )

    @field_validator("url")
    @classmethod
    def normalize_url(cls, value: str) -> str:
        """Remove trailing separators while preserving the URL scheme."""

        value = value.strip().rstrip("/")
        if not value:
            raise ValueError("url must not be blank")
        return value

    @field_validator("api_path")
    @classmethod
    def normalize_api_path(cls, value: str) -> str:
        """Require an absolute HTTP API path without trailing separators."""

        value = value.strip()
        if not value.startswith("/"):
            raise ValueError("api_path must start with '/'")
        return value.rstrip("/") or "/"
