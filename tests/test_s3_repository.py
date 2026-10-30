import asyncio
from datetime import UTC, datetime
from pathlib import Path
import tempfile
import threading
import time
import unittest

from botocore.exceptions import ClientError

from app.common.settings.s3 import S3Settings
from app.repository.exceptions import S3ObjectNotFoundError
from app.repository.s3.boto3_repository import S3Repository as Boto3S3Repository


class FakePaginator:
    def __init__(self, pages: list[dict]) -> None:
        self.pages = pages
        self.parameters: dict | None = None

    def paginate(self, **parameters):
        self.parameters = parameters
        return iter(self.pages)


class FakeS3Client:
    def __init__(
        self,
        pages: list[dict] | None = None,
        head_error: ClientError | None = None,
        download_error: ClientError | None = None,
    ) -> None:
        self.paginator = FakePaginator(pages or [])
        self.head_error = head_error
        self.download_error = download_error
        self.closed_count = 0
        self.downloads: list[tuple[str, str, str]] = []
        self.active_downloads = 0
        self.maximum_active_downloads = 0
        self._lock = threading.Lock()
        self.buckets = {"documents", "models"}
        self.claim_keys: set[tuple[str, str]] = set()
        self.claim_owners: dict[tuple[str, str], str] = {}
        self.deleted: list[tuple[str, str]] = []
        self.copies: list[dict] = []

    def list_buckets(self):
        return {
            "Buckets": [
                {
                    "Name": "documents",
                    "CreationDate": datetime(2026, 1, 1, tzinfo=UTC),
                }
            ]
        }

    def get_paginator(self, operation_name: str):
        if operation_name != "list_objects_v2":
            raise AssertionError(operation_name)
        return self.paginator

    def head_object(self, *, Bucket: str, Key: str):
        if self.head_error is not None:
            raise self.head_error
        return {
            "ContentLength": 0 if (Bucket, Key) in self.claim_keys else 42,
            "ETag": '"etag-value"',
            "ContentType": "application/pdf",
            "LastModified": datetime(2026, 1, 2, tzinfo=UTC),
            "Metadata": (
                {"owner": self.claim_owners[(Bucket, Key)]}
                if (Bucket, Key) in self.claim_keys
                else {}
            ),
        }

    def head_bucket(self, *, Bucket: str):
        if Bucket not in self.buckets:
            raise ClientError(
                {"Error": {"Code": "404", "Message": "Not Found"}},
                "HeadBucket",
            )
        return {}

    def create_bucket(self, **parameters):
        self.buckets.add(parameters["Bucket"])
        return {}

    def put_object(self, *, Bucket: str, Key: str, **parameters):
        identity = (Bucket, Key)
        if identity in self.claim_keys and parameters.get("IfNoneMatch") == "*":
            raise ClientError(
                {
                    "Error": {
                        "Code": "PreconditionFailed",
                        "Message": "claim exists",
                    },
                    "ResponseMetadata": {"HTTPStatusCode": 412},
                },
                "PutObject",
            )
        self.claim_keys.add(identity)
        self.claim_owners[identity] = parameters["Metadata"]["owner"]
        return {}

    def copy_object(self, **parameters):
        self.copies.append(parameters)
        return {}

    def delete_object(self, *, Bucket: str, Key: str, IfMatch: str | None = None):
        self.deleted.append((Bucket, Key))
        self.claim_keys.discard((Bucket, Key))
        self.claim_owners.pop((Bucket, Key), None)
        return {}

    def download_file(
        self,
        bucket: str,
        key: str,
        destination: str,
        Config=None,
    ) -> None:
        if self.download_error is not None:
            raise self.download_error
        with self._lock:
            self.active_downloads += 1
            self.maximum_active_downloads = max(
                self.maximum_active_downloads,
                self.active_downloads,
            )
        try:
            time.sleep(0.01)
            Path(destination).write_bytes(key.encode("utf-8"))
            self.downloads.append((bucket, key, destination))
        finally:
            with self._lock:
                self.active_downloads -= 1

    def close(self) -> None:
        self.closed_count += 1


def make_settings(max_concurrency: int = 2) -> S3Settings:
    return S3Settings(
        endpoint_url="http://rustfs:9000",
        access_key="access",
        secret_key="secret",
        max_concurrency=max_concurrency,
    )


class Boto3S3RepositoryTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def not_found_error(operation: str) -> ClientError:
        return ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            operation,
        )

    async def test_lists_buckets(self) -> None:
        repository = Boto3S3Repository(make_settings(), FakeS3Client())

        buckets = await repository.list_buckets()

        self.assertEqual([bucket.name for bucket in buckets], ["documents"])

    async def test_lists_every_paginated_object(self) -> None:
        pages = [
            {
                "Contents": [
                    {
                        "Key": "contracts/a.pdf",
                        "Size": 10,
                        "ETag": '"a"',
                        "LastModified": datetime(2026, 1, 1, tzinfo=UTC),
                    }
                ]
            },
            {
                "Contents": [
                    {
                        "Key": "contracts/b.pdf",
                        "Size": 20,
                        "ETag": '"b"',
                        "LastModified": datetime(2026, 1, 2, tzinfo=UTC),
                    }
                ]
            },
        ]
        client = FakeS3Client(pages)
        repository = Boto3S3Repository(make_settings(), client)

        objects = await repository.list_objects("documents", "contracts/")

        self.assertEqual([item.key for item in objects], ["contracts/a.pdf", "contracts/b.pdf"])
        self.assertEqual(client.paginator.parameters, {"Bucket": "documents", "Prefix": "contracts/"})
        self.assertIsNone(objects[0].content_type)

    async def test_gets_complete_object_metadata(self) -> None:
        repository = Boto3S3Repository(make_settings(), FakeS3Client())

        metadata = await repository.get_object_metadata(
            "documents",
            "contracts/a.pdf",
        )

        self.assertEqual(metadata.bucket, "documents")
        self.assertEqual(metadata.key, "contracts/a.pdf")
        self.assertEqual(metadata.size, 42)
        self.assertEqual(metadata.etag, "etag-value")
        self.assertEqual(metadata.content_type, "application/pdf")

    async def test_creates_missing_application_bucket(self) -> None:
        client = FakeS3Client()
        repository = Boto3S3Repository(make_settings(), client)

        await repository.ensure_bucket("documents-processing")
        await repository.ensure_bucket("documents-processing")

        self.assertIn("documents-processing", client.buckets)

    async def test_conditional_claim_allows_only_one_owner_until_release(self) -> None:
        client = FakeS3Client()
        repository = Boto3S3Repository(make_settings(), client)

        first = await repository.try_acquire_claim(
            "documents-processing",
            "claims/document.lock",
            "job-one",
            999_999_999,
        )
        second = await repository.try_acquire_claim(
            "documents-processing",
            "claims/document.lock",
            "job-two",
            999_999_999,
        )
        await repository.release_claim(
            "documents-processing",
            "claims/document.lock",
            "job-one",
        )

        self.assertTrue(first)
        self.assertFalse(second)
        self.assertIn(
            ("documents-processing", "claims/document.lock"),
            client.deleted,
        )

    async def test_claim_release_refuses_another_owner(self) -> None:
        client = FakeS3Client()
        repository = Boto3S3Repository(make_settings(), client)
        await repository.try_acquire_claim(
            "documents-processing",
            "claims/document.lock",
            "job-one",
            999_999_999,
        )

        released = await repository.release_claim(
            "documents-processing",
            "claims/document.lock",
            "job-two",
        )

        self.assertFalse(released)
        self.assertIn(
            ("documents-processing", "claims/document.lock"),
            client.claim_keys,
        )

    async def test_copies_with_source_metadata_and_deletes_explicitly(self) -> None:
        client = FakeS3Client()
        repository = Boto3S3Repository(make_settings(), client)

        copied = await repository.copy_object(
            "documents",
            "a.pdf",
            "documents-processing",
            "objects/documents/a.pdf",
            "application/pdf",
            {"source-etag": "etag-value"},
        )
        await repository.delete_object("documents", "a.pdf")

        self.assertEqual(copied.bucket, "documents-processing")
        self.assertEqual(client.copies[0]["MetadataDirective"], "REPLACE")
        self.assertEqual(
            client.deleted,
            [("documents", "a.pdf")],
        )

    async def test_translates_missing_head_to_common_repository_error(self) -> None:
        provider_error = self.not_found_error("HeadObject")
        repository = Boto3S3Repository(
            make_settings(),
            FakeS3Client(head_error=provider_error),
        )

        with self.assertRaises(S3ObjectNotFoundError) as raised:
            await repository.get_object_metadata(
                "documents",
                "contracts/missing.pdf",
            )

        self.assertEqual(raised.exception.bucket, "documents")
        self.assertEqual(raised.exception.object_key, "contracts/missing.pdf")
        self.assertIs(raised.exception.__cause__, provider_error)

    async def test_downloads_exact_object_atomically(self) -> None:
        client = FakeS3Client()
        repository = Boto3S3Repository(make_settings(), client)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "nested/a.pdf"

            result = await repository.download_object(
                "documents",
                "contracts/a.pdf",
                destination,
            )

            self.assertEqual(result, destination)
            self.assertEqual(destination.read_bytes(), b"contracts/a.pdf")
            self.assertFalse(destination.with_name(".a.pdf.part").exists())

    async def test_translates_missing_download_and_removes_partial_file(self) -> None:
        provider_error = self.not_found_error("GetObject")
        client = FakeS3Client(download_error=provider_error)
        repository = Boto3S3Repository(make_settings(), client)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "missing.pdf"

            with self.assertRaises(S3ObjectNotFoundError) as raised:
                await repository.download_object(
                    "documents",
                    "missing.pdf",
                    destination,
                )

            self.assertIs(raised.exception.__cause__, provider_error)
            self.assertFalse(destination.with_name(".missing.pdf.part").exists())

    async def test_downloads_prefix_with_bounded_concurrency(self) -> None:
        contents = [
            {
                "Key": f"embeddings/file-{number}.bin",
                "Size": number,
                "ETag": f'"{number}"',
            }
            for number in range(5)
        ]
        client = FakeS3Client([{"Contents": contents}])
        repository = Boto3S3Repository(
            make_settings(max_concurrency=2),
            client,
        )
        with tempfile.TemporaryDirectory() as directory:
            paths = await repository.download_prefix(
                "models",
                "embeddings",
                Path(directory),
            )

            self.assertEqual(len(paths), 5)
            self.assertLessEqual(client.maximum_active_downloads, 2)
            self.assertTrue((Path(directory) / "file-4.bin").exists())

    async def test_rejects_unsafe_key_during_prefix_download(self) -> None:
        client = FakeS3Client(
            [{"Contents": [{"Key": "embeddings/../secret", "Size": 1}]}]
        )
        repository = Boto3S3Repository(make_settings(), client)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "unsafe object key"):
                await repository.download_prefix(
                    "models",
                    "embeddings",
                    Path(directory),
                )

    async def test_cleanup_is_idempotent_and_closed_repository_rejects_calls(self) -> None:
        client = FakeS3Client()
        repository = Boto3S3Repository(make_settings(), client)

        await repository.close()
        await repository.close()

        self.assertEqual(client.closed_count, 1)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            await repository.list_buckets()


if __name__ == "__main__":
    unittest.main()
