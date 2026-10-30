import unittest

import httpx

from app.common.settings.embedding_service import EmbeddingProvider, EmbeddingServiceSettings
from app.repository.embedding_service.factory import EmbeddingRepositoryFactory
from app.repository.embedding_service.enterprise_embedding_service_repository import (
    EnterpriseEmbeddingServiceRepository,
)
from app.repository.embedding_service.exceptions import EmbeddingServiceRequestError


class EnterpriseEmbeddingServiceRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_factory_defaults_to_httpx_and_preserves_injected_client(self) -> None:
        client = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(500)
            )
        )

        factory = EmbeddingRepositoryFactory()
        factory.register(EmbeddingProvider.HTTPX, EnterpriseEmbeddingServiceRepository)
        repository = factory.create(
            EmbeddingProvider.HTTPX,
            client,
            EmbeddingServiceSettings(),
        )

        self.assertIs(repository._httpx_client, client)
        await repository.close()
        self.assertTrue(client.is_closed)

    async def test_close_is_idempotent_and_closes_httpx_client(self) -> None:
        client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
        repository = EnterpriseEmbeddingServiceRepository(
            client,
            EmbeddingServiceSettings(),
        )

        await repository.close()
        await repository.close()

        self.assertTrue(client.is_closed)

    async def test_uses_injected_client_and_validates_vectors(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                json={
                    "model": "intfloat/multilingual-e5-small",
                    "dimension": 2,
                    "normalized": True,
                    "embeddings": [[0.6, 0.8]],
                },
            )

        client = httpx.AsyncClient(
            base_url="http://embedding.test",
            transport=httpx.MockTransport(handler),
        )
        repository = EnterpriseEmbeddingServiceRepository(
            client,
            EmbeddingServiceSettings(
                expected_dimension=2,
                max_batch_size=2,
            ),
        )

        vectors = await repository.embed(("a document chunk",))

        self.assertEqual(vectors, ((0.6, 0.8),))
        self.assertEqual(requests[0].url.path, "/v1/embeddings")
        self.assertEqual(requests[0].content, b'{"input_type":"document","texts":["a document chunk"]}')
        await repository.close()

    async def test_rejects_wrong_dimension(self) -> None:
        client = httpx.AsyncClient(
            base_url="http://embedding.test",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "model": "intfloat/multilingual-e5-small",
                        "dimension": 3,
                        "normalized": True,
                        "embeddings": [[0.1, 0.2, 0.3]],
                    },
                )
            ),
        )
        repository = EnterpriseEmbeddingServiceRepository(
            client,
            EmbeddingServiceSettings(expected_dimension=2),
        )

        with self.assertRaisesRegex(RuntimeError, "unexpected dimension"):
            await repository.embed(("chunk",))
        await repository.close()

    async def test_accepts_exact_character_limit_and_rejects_one_over(self) -> None:
        client = httpx.AsyncClient(
            base_url="http://embedding.test",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    json={
                        "model": "intfloat/multilingual-e5-small",
                        "dimension": 2,
                        "normalized": True,
                        "embeddings": [[0.6, 0.8]],
                    },
                )
            ),
        )
        repository = EnterpriseEmbeddingServiceRepository(
            client,
            EmbeddingServiceSettings(
                expected_dimension=2,
                max_text_characters=5,
            ),
        )

        self.assertEqual(await repository.embed(("12345",)), ((0.6, 0.8),))
        with self.assertRaisesRegex(ValueError, "max text characters"):
            await repository.embed(("123456",))
        await repository.close()

    async def test_translates_rejected_response_with_safe_detail(self) -> None:
        client = httpx.AsyncClient(
            base_url="http://embedding.test",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    413,
                    json={"detail": "embedding input is too large"},
                )
            ),
        )
        repository = EnterpriseEmbeddingServiceRepository(
            client,
            EmbeddingServiceSettings(),
        )

        with self.assertRaisesRegex(
            EmbeddingServiceRequestError,
            "HTTP 413: embedding input is too large",
        ):
            await repository.embed(("chunk",))
        await repository.close()


if __name__ == "__main__":
    unittest.main()
