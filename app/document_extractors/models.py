"""Validated output models shared by document text extractors."""

from pydantic import BaseModel, ConfigDict, Field


class ExtractedPage(BaseModel):
    """Embedded text extracted from one one-based document page."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page_number: int = Field(ge=1)
    text: str
