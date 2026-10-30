"""Exceptions raised by embedding-service repository adapters."""


class EmbeddingServiceRequestError(RuntimeError):
    """Report a rejected embedding request without exposing response internals."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(
            f"embedding service rejected request with HTTP {status_code}: {detail}"
        )


__all__ = ["EmbeddingServiceRequestError"]
