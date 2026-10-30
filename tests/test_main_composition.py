import unittest

from app.common.settings.embedding_service import EmbeddingServiceSettings
from app.jobs.base import IndexingJobArguments
from app.main import create_embedding_http_client


class MainCompositionTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_pool_is_bounded_by_cli_concurrency(self) -> None:
        client = create_embedding_http_client(
            IndexingJobArguments(
                source_bucket="documents",
                concurrency=2,
            ),
            EmbeddingServiceSettings(
                url="http://embedding.test",
                max_connections=8,
                max_keepalive_connections=6,
            ),
        )

        pool = client._transport._pool
        self.assertEqual(pool._max_connections, 2)
        self.assertEqual(pool._max_keepalive_connections, 2)
        await client.aclose()

    async def test_environment_limit_caps_larger_cli_concurrency(self) -> None:
        client = create_embedding_http_client(
            IndexingJobArguments(
                source_bucket="documents",
                concurrency=12,
            ),
            EmbeddingServiceSettings(
                url="http://embedding.test",
                max_connections=5,
                max_keepalive_connections=3,
            ),
        )

        pool = client._transport._pool
        self.assertEqual(pool._max_connections, 5)
        self.assertEqual(pool._max_keepalive_connections, 3)
        await client.aclose()


if __name__ == "__main__":
    unittest.main()
