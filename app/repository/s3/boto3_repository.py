"""RustFS-compatible S3 repository implemented with boto3."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import Any, TypeVar

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from boto3.s3.transfer import TransferConfig

from app.common.settings.s3 import S3Settings
from app.common.utility.paths import safe_object_destination
from app.repository.models import S3Bucket, S3ObjectMetadata
from app.repository.exceptions import S3ObjectNotFoundError
from app.repository.s3.base import S3Repository

LOGGER = logging.getLogger(__name__)
ResultT = TypeVar("ResultT")


class Boto3S3Repository(S3Repository):
    """Expose bounded asynchronous S3 operations over blocking boto3 calls.

    Args:
        settings: Validated endpoint, credentials, TLS and concurrency values.
        client: Optional boto3-compatible client used by unit tests.

    Notes:
        Every boto3 call crosses ``asyncio.to_thread`` while an internal
        semaphore limits blocking work. Call :meth:`close` during application
        cleanup; it is safe to call repeatedly.
    """

    def __init__(self, settings: S3Settings, client: Any | None = None) -> None:
        self._settings = settings
        self._client = client or boto3.client(
            "s3",
            endpoint_url=str(settings.endpoint_url),
            aws_access_key_id=settings.access_key,
            aws_secret_access_key=settings.secret_key.get_secret_value(),
            region_name=settings.region,
            verify=settings.verify_tls,
            config=Config(
                s3={"addressing_style": settings.addressing_style},
            ),
        )
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)
        self._transfer_config = TransferConfig(use_threads=False)
        self._closed = False

    async def list_buckets(self) -> list[S3Bucket]:
        """Return accessible buckets without exposing credential details."""

        response = await self._call(self._client.list_buckets)
        return [
            S3Bucket(
                name=item["Name"],
                creation_date=item.get("CreationDate"),
            )
            for item in response.get("Buckets", [])
        ]

    async def list_objects(
        self,
        bucket: str,
        key_prefix: str | None = None,
    ) -> list[S3ObjectMetadata]:
        """List all objects across every ``list_objects_v2`` page.

        List responses do not include content type, so returned records set
        ``content_type`` to ``None``. Use :meth:`get_object_metadata` before
        content-type-based document routing.
        """

        self._ensure_open()
        paginator = self._client.get_paginator("list_objects_v2")
        parameters: dict[str, str] = {"Bucket": bucket}
        if key_prefix is not None:
            parameters["Prefix"] = key_prefix

        pages = await self._call(lambda: list(paginator.paginate(**parameters)))
        objects: list[S3ObjectMetadata] = []
        for page in pages:
            for item in page.get("Contents", []):
                objects.append(
                    S3ObjectMetadata(
                        bucket=bucket,
                        key=item["Key"],
                        size=item["Size"],
                        etag=self._normalize_etag(item.get("ETag")),
                        content_type=None,
                        last_modified=item.get("LastModified"),
                    )
                )
        LOGGER.info(
            "listed S3 objects bucket=%s key_prefix=%s objects=%d",
            bucket,
            key_prefix,
            len(objects),
        )
        return objects

    async def get_object_metadata(
        self,
        bucket: str,
        object_key: str,
    ) -> S3ObjectMetadata:
        """Resolve complete object metadata using ``head_object``."""

        try:
            response = await self._call(
                self._client.head_object,
                Bucket=bucket,
                Key=object_key,
            )
        except ClientError as error:
            self._raise_if_object_not_found(error, bucket, object_key)
            raise
        return S3ObjectMetadata(
            bucket=bucket,
            key=object_key,
            size=response["ContentLength"],
            etag=self._normalize_etag(response.get("ETag")),
            content_type=response.get("ContentType"),
            last_modified=response.get("LastModified"),
            user_metadata=response.get("Metadata", {}),
        )

    async def ensure_bucket(self, bucket: str) -> None:
        """Create ``bucket`` when it does not already exist."""

        try:
            await self._call(self._client.head_bucket, Bucket=bucket)
            return
        except ClientError as error:
            error_code = str(error.response.get("Error", {}).get("Code", ""))
            if error_code not in {"404", "NoSuchBucket", "NotFound"}:
                raise

        parameters: dict[str, Any] = {"Bucket": bucket}
        if self._settings.region != "us-east-1":
            parameters["CreateBucketConfiguration"] = {
                "LocationConstraint": self._settings.region,
            }
        await self._call(self._client.create_bucket, **parameters)
        LOGGER.info("created S3 bucket bucket=%s", bucket)

    async def try_acquire_claim(
        self,
        bucket: str,
        claim_key: str,
        owner: str,
        stale_after_seconds: int,
    ) -> bool:
        """Acquire a claim with ``If-None-Match`` and reclaim stale markers."""

        if await self._put_claim_if_absent(bucket, claim_key, owner):
            return True
        try:
            existing = await self.get_object_metadata(bucket, claim_key)
        except S3ObjectNotFoundError:
            return await self._put_claim_if_absent(bucket, claim_key, owner)
        if existing.last_modified is None:
            return False
        age_seconds = (datetime.now(UTC) - existing.last_modified).total_seconds()
        if age_seconds < stale_after_seconds:
            return False
        if existing.etag is None or not await self._delete_if_match(
            bucket,
            claim_key,
            existing.etag,
        ):
            return False
        acquired = await self._put_claim_if_absent(bucket, claim_key, owner)
        if acquired:
            LOGGER.warning(
                "reclaimed stale S3 claim bucket=%s claim_key=%s age_seconds=%.0f",
                bucket,
                claim_key,
                age_seconds,
            )
        return acquired

    async def release_claim(
        self,
        bucket: str,
        claim_key: str,
        owner: str,
    ) -> bool:
        """Release only the marker still owned by ``owner`` and its ETag."""

        try:
            existing = await self.get_object_metadata(bucket, claim_key)
        except S3ObjectNotFoundError:
            return True
        if existing.user_metadata.get("owner") != owner:
            LOGGER.warning(
                "refused to release S3 claim owned by another job "
                "bucket=%s claim_key=%s",
                bucket,
                claim_key,
            )
            return False
        if existing.etag is None:
            return False
        return await self._delete_if_match(bucket, claim_key, existing.etag)

    async def copy_object(
        self,
        source_bucket: str,
        source_key: str,
        destination_bucket: str,
        destination_key: str,
        content_type: str | None,
        user_metadata: dict[str, str],
    ) -> S3ObjectMetadata:
        """Copy one S3 object while replacing its operational metadata."""

        parameters: dict[str, Any] = {
            "Bucket": destination_bucket,
            "Key": destination_key,
            "CopySource": {"Bucket": source_bucket, "Key": source_key},
            "Metadata": user_metadata,
            "MetadataDirective": "REPLACE",
        }
        if content_type is not None:
            parameters["ContentType"] = content_type
        await self._call(self._client.copy_object, **parameters)
        return await self.get_object_metadata(destination_bucket, destination_key)

    async def delete_object(self, bucket: str, object_key: str) -> None:
        """Delete one exact object without logging its contents."""

        await self._call(
            self._client.delete_object,
            Bucket=bucket,
            Key=object_key,
        )

    async def _put_claim_if_absent(
        self,
        bucket: str,
        claim_key: str,
        owner: str,
    ) -> bool:
        try:
            await self._call(
                self._client.put_object,
                Bucket=bucket,
                Key=claim_key,
                Body=b"",
                ContentType="application/octet-stream",
                Metadata={"owner": owner},
                IfNoneMatch="*",
            )
            return True
        except ClientError as error:
            error_code = str(error.response.get("Error", {}).get("Code", ""))
            status_code = error.response.get("ResponseMetadata", {}).get(
                "HTTPStatusCode"
            )
            if error_code in {
                "409",
                "412",
                "ConditionalRequestConflict",
                "PreconditionFailed",
            } or status_code in {409, 412}:
                return False
            raise

    async def _delete_if_match(
        self,
        bucket: str,
        object_key: str,
        etag: str,
    ) -> bool:
        try:
            await self._call(
                self._client.delete_object,
                Bucket=bucket,
                Key=object_key,
                IfMatch=etag,
            )
            return True
        except ClientError as error:
            error_code = str(error.response.get("Error", {}).get("Code", ""))
            status_code = error.response.get("ResponseMetadata", {}).get(
                "HTTPStatusCode"
            )
            if error_code in {"PreconditionFailed", "412"} or status_code == 412:
                return False
            raise

    async def download_object(
        self,
        bucket: str,
        object_key: str,
        destination: Path,
    ) -> Path:
        """Download one object through a temporary file and atomic replace.

        Args:
            bucket: Bucket containing the object.
            object_key: Exact key to download.
            destination: Final local file path.

        Returns:
            The supplied final destination.

        Raises:
            BaseException: Propagates boto3 and filesystem errors after
                removing a partial download when possible.
        """

        self._ensure_open()
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial_destination = destination.with_name(f".{destination.name}.part")
        try:
            await self._call(
                self._client.download_file,
                bucket,
                object_key,
                str(partial_destination),
                Config=self._transfer_config,
            )
            partial_destination.replace(destination)
        except ClientError as error:
            partial_destination.unlink(missing_ok=True)
            self._raise_if_object_not_found(error, bucket, object_key)
            raise
        except BaseException:
            partial_destination.unlink(missing_ok=True)
            raise

        LOGGER.info(
            "downloaded S3 object bucket=%s object_key=%s destination=%s",
            bucket,
            object_key,
            destination,
        )
        return destination

    async def download_prefix(
        self,
        bucket: str,
        key_prefix: str,
        destination_directory: Path,
    ) -> list[Path]:
        """Download every object below ``key_prefix`` in bounded batches.

        Prefix components are removed from local paths. Directory marker
        objects are skipped, and unsafe relative keys fail before writing.
        Existing files are replaced atomically; unrelated local files are not
        deleted.
        """

        normalized_prefix = key_prefix.strip("/")
        if not normalized_prefix:
            raise ValueError("key_prefix must not be blank")
        object_prefix = f"{normalized_prefix}/"
        objects = await self.list_objects(bucket, object_prefix)

        downloads: list[tuple[S3ObjectMetadata, Path]] = []
        for item in objects:
            if item.key.endswith("/"):
                continue
            relative_key = item.key.removeprefix(object_prefix)
            if relative_key == item.key:
                raise ValueError(
                    f"listed object is outside requested prefix: {item.key}"
                )
            destination = safe_object_destination(
                destination_directory,
                relative_key,
            )
            downloads.append((item, destination))

        downloaded_paths: list[Path] = []
        batch_size = self._settings.max_concurrency
        for offset in range(0, len(downloads), batch_size):
            batch = downloads[offset : offset + batch_size]
            downloaded_paths.extend(
                await asyncio.gather(
                    *(
                        self.download_object(bucket, item.key, destination)
                        for item, destination in batch
                    )
                )
            )

        LOGGER.info(
            "downloaded S3 prefix bucket=%s key_prefix=%s files=%d "
            "destination=%s",
            bucket,
            normalized_prefix,
            len(downloaded_paths),
            destination_directory,
        )
        return downloaded_paths

    async def close(self) -> None:
        """Close the boto3 client once without logging connection secrets."""

        if self._closed:
            return
        async with self._semaphore:
            await asyncio.to_thread(self._client.close)
        self._closed = True
        LOGGER.info("S3 repository closed")

    async def _call(
        self,
        operation: Callable[..., ResultT],
        *args: Any,
        **kwargs: Any,
    ) -> ResultT:
        self._ensure_open()
        async with self._semaphore:
            return await asyncio.to_thread(operation, *args, **kwargs)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("S3 repository is closed")

    @staticmethod
    def _normalize_etag(value: Any) -> str | None:
        if value is None:
            return None
        return str(value).strip('"')

    @staticmethod
    def _raise_if_object_not_found(
        error: ClientError,
        bucket: str,
        object_key: str,
    ) -> None:
        error_code = str(error.response.get("Error", {}).get("Code", ""))
        if error_code in {"404", "NoSuchKey", "NotFound"}:
            raise S3ObjectNotFoundError(bucket, object_key) from error
