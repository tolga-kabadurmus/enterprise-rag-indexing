"""Provider selection settings for vector persistence."""

from enum import Enum

from pydantic_settings import BaseSettings, SettingsConfigDict


class VectorProvider(str, Enum):
    """Supported vector repository provider keys."""

    QDRANT = "qdrant"


class VectorSettings(BaseSettings):
    """Select the vector repository provider without exposing its technology."""

    model_config = SettingsConfigDict(
        env_prefix="VECTOR_",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    provider: VectorProvider = VectorProvider.QDRANT
