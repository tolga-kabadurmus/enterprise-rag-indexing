"""Provider-neutral S3 repository contract."""

from abc import abstractmethod
from pathlib import Path

from app.repository.base import Repository
from app.repository.models import S3Bucket, S3ObjectMetadata


class S3Repository(Repository):
    """Async boundary for the S3 operations required by indexing pipelines."""

    @abstractmethod
    async def list_buckets(self) -> list[S3Bucket]:
        """Return every bucket visible to the configured credentials."""

    @abstractmethod
    async def list_objects(
        self,
        bucket: str,
        key_prefix: str | None = None,
    ) -> list[S3ObjectMetadata]:
        """Return every object using paginated discovery."""

    @abstractmethod
    async def get_object_metadata(
        self,
        bucket: str,
        object_key: str,
    ) -> S3ObjectMetadata:
        """Return metadata resolved with ``head_object``."""

    @abstractmethod
    async def download_object(
        self,
        bucket: str,
        object_key: str,
        destination: Path,
    ) -> Path:
        """Download one object atomically to a local file."""

    @abstractmethod
    async def download_prefix(
        self,
        bucket: str,
        key_prefix: str,
        destination_directory: Path,
    ) -> list[Path]:
        """Download all objects below a prefix, preserving relative paths."""
