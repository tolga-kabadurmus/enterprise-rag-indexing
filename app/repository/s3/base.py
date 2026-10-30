"""Provider-neutral S3 repository contract."""

from abc import abstractmethod
from pathlib import Path

from app.repository.base import Repository
from app.repository.models import S3Bucket, S3ObjectMetadata


class StorageRepositoryBase(Repository):
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
    async def ensure_bucket(self, bucket: str) -> None:
        """Ensure an application-owned bucket exists."""

    @abstractmethod
    async def try_acquire_claim(
        self,
        bucket: str,
        claim_key: str,
        owner: str,
        stale_after_seconds: int,
    ) -> bool:
        """Atomically create a claim marker, reclaiming stale markers."""

    @abstractmethod
    async def release_claim(
        self,
        bucket: str,
        claim_key: str,
        owner: str,
    ) -> bool:
        """Conditionally delete an owned claim marker.

        Returns:
            ``True`` when the owned marker was removed or no longer exists;
            ``False`` when another owner holds it or its ETag changed.
        """

    @abstractmethod
    async def copy_object(
        self,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
        content_type: str | None,
        user_metadata: dict[str, str],
    ) -> S3ObjectMetadata:
        """Copy one object and return verified destination metadata."""

    @abstractmethod
    async def delete_object(self, bucket: str, object_key: str) -> None:
        """Delete one exact object."""

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
