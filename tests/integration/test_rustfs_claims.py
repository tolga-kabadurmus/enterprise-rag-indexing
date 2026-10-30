import os
import unittest
from uuid import uuid4

from app.common.settings.s3 import S3Settings
from app.repository.factory import RepositoryFactory


@unittest.skipUnless(
    os.getenv("RUN_RUSTFS_INTEGRATION") == "1",
    "set RUN_RUSTFS_INTEGRATION=1 for live RustFS tests",
)
class RustFSClaimIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_conditional_claim_has_one_winner(self) -> None:
        settings = S3Settings()
        repository = RepositoryFactory.create_s3(settings)
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
