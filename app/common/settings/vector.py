"""Provider selection settings for vector persistence."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VectorSettings(BaseSettings):
    """Select the vector repository provider without exposing its technology."""

    model_config = SettingsConfigDict(
        env_prefix="VECTOR_",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    provider: str = Field(default="qdrant", min_length=1)
