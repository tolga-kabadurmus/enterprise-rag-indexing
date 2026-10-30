"""Validated S3-compatible storage settings."""

from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class S3Settings(BaseSettings):
    """Connection and bounded-execution settings for an S3-compatible service.

    Values are read from variables prefixed with ``S3_``. Credentials are
    represented by ``SecretStr`` so their values are not exposed by normal
    model rendering or logging.
    """

    model_config = SettingsConfigDict(
        env_prefix="S3_",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    provider: Literal["rustfs"] = "rustfs"
    endpoint_url: AnyHttpUrl
    access_key: str = Field(min_length=1)
    secret_key: SecretStr
    region: str = Field(default="us-east-1", min_length=1)
    addressing_style: Literal["path", "virtual", "auto"] = "path"
    verify_tls: bool = True
    max_concurrency: int = Field(default=4, ge=1)
    processing_bucket: str = Field(
        default="documents-processing",
        min_length=1,
    )
    claim_ttl_seconds: int = Field(default=3600, ge=60)
