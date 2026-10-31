"""Validated settings for Qdrant vector persistence."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class QdrantSettings(BaseSettings):
    """Configure the Qdrant collection used by the indexing job."""

    model_config = SettingsConfigDict(
        env_prefix="QDRANT_",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    url: str = Field(default="http://qdrant:6333", min_length=1)
    api_key: SecretStr | None = None
    collection_name: str = Field(default="enterprise_rag_chunks", min_length=1)
    dense_vector_name: str = Field(default="dense", min_length=1)
    sparse_vector_name: str = Field(default="sparse", min_length=1)
    vector_size: int = Field(default=384, ge=1)
    batch_size: int = Field(default=64, ge=1)
    timeout_seconds: int = Field(default=30, ge=1)
    max_retries: int = Field(default=3, ge=1, le=10)
    retry_base_seconds: float = Field(default=0.25, ge=0)
    create_collection_if_missing: bool = True

