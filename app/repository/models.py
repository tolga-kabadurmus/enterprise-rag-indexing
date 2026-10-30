"""Validated records returned by repository boundaries."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class S3Bucket(BaseModel):
    """One bucket returned by the S3 service."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    creation_date: datetime | None = None


class S3ObjectMetadata(BaseModel):
    """Source identity and metadata for one S3-compatible object."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bucket: str = Field(min_length=1)
    key: str = Field(min_length=1)
    size: int = Field(ge=0)
    etag: str | None = None
    content_type: str | None = None
    last_modified: datetime | None = None
