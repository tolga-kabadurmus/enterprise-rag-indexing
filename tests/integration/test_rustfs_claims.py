import os
import unittest
from uuid import uuid4

from app.common.settings.s3 import S3Settings
from app.common.settings.s3 import StorageProvider
from app.repository.s3.boto3_repository import S3Repository
from app.repository.s3.factory import StorageRepositoryFactory


@unittest.skipUnless(
    os.getenv("RUN_RUSTFS_INTEGRATION") == "1",
    "set RUN_RUSTFS_INTEGRATION=1 for live RustFS tests",
)
class RustFSClaimIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_conditional_claim_has_one_winner(self) -> None:
        settings = S3Settings()
        factory = StorageRepositoryFactory()
        factory.register(StorageProvider.RUSTFS, S3Repository)
        repository = factory.create(settings.provider, settings)
        claim_key = f"claims/integration-{uuid4()}.lock"
        try:
            await repository.ensure_bucket(settings.processing_bucket)
            first = await repository.try_acquire_claim(
                settings.processing_bucket,
                claim_key,
                "integration-one",
                settings.claim_ttl_seconds,
            )
            second = await repository.try_acquire_claim(
                settings.processing_bucket,
                claim_key,
                "integration-two",
                settings.claim_ttl_seconds,
            )

            self.assertTrue(first)
            self.assertFalse(second)
        finally:
            if "first" in locals() and first:
                await repository.release_claim(
                    settings.processing_bucket,
                    claim_key,
                    "integration-one",
                )
            await repository.close()


if __name__ == "__main__":
    unittest.main()
