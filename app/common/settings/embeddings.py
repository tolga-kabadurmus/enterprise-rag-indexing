"""Validated settings for embedding model artifacts."""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingModelSettings(BaseSettings):
    """Location of embedding model artifacts in S3 and in the container.

    Values are read from variables prefixed with ``EMBEDDINGS_``. The bucket,
    key prefix, and local directory are configurable independently.
    """

    model_config = SettingsConfigDict(
        env_prefix="EMBEDDINGS_",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    bucket: str = Field(default="models", min_length=1)
    key_prefix: str = Field(default="embeddings", min_length=1)
    local_directory: Path = Path("/models/embeddings")
    runtime: Literal["onnx"] = "onnx"
    model_file: Path = Path("onnx/model.onnx")

    @field_validator("bucket", "key_prefix")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        """Normalize surrounding separators and reject blank values."""

        normalized = value.strip().strip("/")
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("local_directory")
    @classmethod
    def require_absolute_directory(cls, value: Path) -> Path:
        """Require an absolute model directory inside the container."""

        if not value.is_absolute():
            raise ValueError("local_directory must be an absolute path")
        return value

    @field_validator("model_file")
    @classmethod
    def require_safe_relative_model_file(cls, value: Path) -> Path:
        """Require a model artifact path relative to ``local_directory``."""

        if value.is_absolute() or ".." in value.parts or not value.name:
            raise ValueError("model_file must be a safe relative path")
        return value

    @property
    def model_path(self) -> Path:
        """Return the configured model artifact's absolute local path."""

        return self.local_directory / self.model_file
