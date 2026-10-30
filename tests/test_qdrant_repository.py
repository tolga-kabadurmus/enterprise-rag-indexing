import unittest
from types import SimpleNamespace

from qdrant_client import models

from app.common.settings.qdrant import QdrantSettings
from app.common.settings.vector import VectorProvider
from app.repository.vector.base import SparseVector, VectorPoint, VectorRepositoryBase
from app.repository.vector.factory import VectorRepositoryFactory
from app.repository.vector.qdrant_repository import QdrantVectorRepository


class FakeQdrantClient:
    def __init__(self, exists: bool = True) -> None:
        self.exists = exists
        self.created = False
        self.upserts = []
        self.closed = False

    async def collection_exists(self, collection_name: str) -> bool:
        return self.exists

    async def create_collection(self, **kwargs) -> None:
        self.created = True
        self.exists = True

    async def get_collection(self, collection_name: str):
        params = SimpleNamespace(
            vectors={
                "dense": models.VectorParams(
                    size=384,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors={"sparse": models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        return SimpleNamespace(config=SimpleNamespace(params=params))

    async def upsert(self, **kwargs):
        self.upserts.append(kwargs)

    async def close(self) -> None:
        self.closed = True


class QdrantVectorRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_creates_missing_hybrid_ready_collection(self) -> None:
        client = FakeQdrantClient(exists=False)
        repository = QdrantVectorRepository(client, QdrantSettings())

        await repository.ensure_collection()

        self.assertTrue(client.created)

    async def test_upserts_named_dense_and_optional_sparse_vectors(self) -> None:
        client = FakeQdrantClient()
        repository = QdrantVectorRepository(
            client,
            QdrantSettings(batch_size=1),
        )
        points = (
            VectorPoint(
                point_id="31f80e75-8cf7-5ed4-b7f2-64cb545d36d7",
                dense_vector=tuple(0.0 for _ in range(384)),
                sparse_vector=SparseVector(indices=(1, 9), values=(0.5, 0.8)),
                payload={"document_id": "doc", "object_key": "contracts/a.pdf"},
            ),
        )

        await repository.upsert_points(points)

        stored = client.upserts[0]["points"][0]
        self.assertIn("dense", stored.vector)
        self.assertIn("sparse", stored.vector)
        self.assertEqual(stored.id, points[0].point_id)
        self.assertEqual(stored.payload["object_key"], "contracts/a.pdf")

    async def test_close_is_idempotent(self) -> None:
        client = FakeQdrantClient()
        repository = QdrantVectorRepository(client, QdrantSettings())

        await repository.close()
        await repository.close()

        self.assertTrue(client.closed)


class VectorRepositoryFactoryTests(unittest.TestCase):
    def test_registered_qdrant_implementation_is_created_through_contract(self) -> None:
        factory = VectorRepositoryFactory()
        factory.register(VectorProvider.QDRANT, QdrantVectorRepository)

        repository = factory.create(
            VectorProvider.QDRANT,
            FakeQdrantClient(),
            QdrantSettings(),
        )

        self.assertIsInstance(repository, VectorRepositoryBase)
        self.assertIsInstance(repository, QdrantVectorRepository)

    def test_unknown_provider_is_rejected(self) -> None:
        factory = VectorRepositoryFactory()

        with self.assertRaisesRegex(ValueError, "unsupported vector provider"):
            factory.create(VectorProvider.QDRANT)

    def test_duplicate_provider_registration_is_rejected(self) -> None:
        factory = VectorRepositoryFactory()
        factory.register(VectorProvider.QDRANT, QdrantVectorRepository)

        with self.assertRaisesRegex(ValueError, "already registered"):
            factory.register(VectorProvider.QDRANT, QdrantVectorRepository)


if __name__ == "__main__":
    unittest.main()
