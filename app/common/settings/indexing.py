"""Validated settings for the indexing job's temporary workspace."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class IndexingWorkspaceSettings(BaseSettings):
    """Configure the ephemeral local workspace used by one-shot jobs."""

    model_config = SettingsConfigDict(
        env_prefix="INDEXING_",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    work_directory: Path = Path("/work/indexing")

    @field_validator("work_directory")
    @classmethod
    def require_absolute_work_directory(cls, value: Path) -> Path:
        """Require a container-absolute ephemeral workspace path."""

        if not value.is_absolute():
            raise ValueError("work_directory must be an absolute path")
        return value
