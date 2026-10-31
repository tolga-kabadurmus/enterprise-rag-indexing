"""Validated settings for text-only PDF chunking."""

from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PDFChunkingSettings(BaseSettings):
    """Configure deterministic character-window chunking for PDF page text."""

    model_config = SettingsConfigDict(
        env_prefix="PDF_CHUNK_",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    size: int = Field(default=1200, ge=100)
    overlap: int = Field(default=200, ge=0)

    @model_validator(mode="after")
    def require_overlap_smaller_than_size(self) -> Self:
        """Reject windows that cannot make forward progress."""

        if self.overlap >= self.size:
            raise ValueError("PDF chunk overlap must be smaller than chunk size")
        return self
