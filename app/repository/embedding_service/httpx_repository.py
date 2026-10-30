"""HTTPX adapter for the shared embedding service."""

from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.common.settings.embedding_service import EmbeddingServiceSettings
from app.repository.embedding_service.base import EmbeddingRepository
from app.repository.embedding_service.exceptions import EmbeddingServiceRequestError


class EmbeddingRequest(BaseModel):
    """Payload accepted by the embedding service."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_type: Literal["document", "query"]
    texts: tuple[str, ...] = Field(min_length=1)


class EmbeddingResponse(BaseModel):
    """Validated response returned by the embedding service."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    model: str
    dimension: int = Field(ge=1)
    normalized: bool
    embeddings: tuple[tuple[float, ...], ...]


class HttpxEmbeddingServiceRepository(EmbeddingRepository):
    """Call the shared embedding API using an injected pooled HTTPX client.

    The client is created by the indexing startup composition layer. This
    repository never creates a client per request, preserving connection
    pooling across concurrently processed documents.
    """

    def __init__(
        self,
        httpx_client: httpx.AsyncClient,
        settings: EmbeddingServiceSettings,
    ) -> None:
        self._httpx_client = httpx_client
        self._settings = settings
        self._closed = False

    @property
    def max_batch_size(self) -> int:
        """Return the configured maximum number of texts per request."""

        return self._settings.max_batch_size

    @property
    def max_text_characters(self) -> int:
        """Return the maximum aggregate text characters per request."""

        return self._settings.max_text_characters

    async def embed(
        self,
        texts: tuple[str, ...],
        input_type: Literal["document", "query"] = "document",
    ) -> tuple[tuple[float, ...], ...]:
        """Vectorize a bounded batch and validate its model contract.

        Raises:
            RuntimeError: If the service returns an invalid model or vectors.
            httpx.HTTPError: If transport or HTTP status handling fails.
        """

        if self._closed:
            raise RuntimeError("embedding service repository is closed")
        if not texts:
            return ()
        if len(texts) > self._settings.max_batch_size:
            raise ValueError(
                "embedding request exceeds max batch size "
                f"({self._settings.max_batch_size})"
            )
        character_count = sum(len(text) for text in texts)
        if character_count > self._settings.max_text_characters:
            raise ValueError(
                "embedding request exceeds max text characters "
                f"({self._settings.max_text_characters})"
            )
        payload = EmbeddingRequest(input_type=input_type, texts=texts)
        response = await self._httpx_client.post(
            self._settings.api_path,
            json=payload.model_dump(mode="json"),
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            detail = "request rejected"
            try:
                response_body = response.json()
                if isinstance(response_body, dict):
                    response_detail = response_body.get("detail")
                    if isinstance(response_detail, str) and response_detail.strip():
                        detail = response_detail.strip()
            except ValueError:
                pass
            raise EmbeddingServiceRequestError(
                response.status_code,
                detail,
            ) from error
        try:
            result = EmbeddingResponse.model_validate(response.json())
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                "embedding service returned an invalid response"
            ) from error
        if result.model != self._settings.expected_model:
            raise RuntimeError(
                "embedding service returned unexpected model "
                f"{result.model!r}"
            )
        if result.dimension != self._settings.expected_dimension:
            raise RuntimeError(
                "embedding service returned unexpected dimension "
                f"{result.dimension}; expected "
                f"{self._settings.expected_dimension}"
            )
        if len(result.embeddings) != len(texts):
            raise RuntimeError("embedding service returned the wrong vector count")
        if any(len(vector) != result.dimension for vector in result.embeddings):
            raise RuntimeError("embedding service returned a wrong vector length")
        return result.embeddings

    async def close(self) -> None:
        """Close the injected client exactly once."""

        if self._closed:
            return
        self._closed = True
        await self._httpx_client.aclose()


__all__ = [
    "EmbeddingRequest",
    "EmbeddingResponse",
    "HttpxEmbeddingServiceRepository",
]
