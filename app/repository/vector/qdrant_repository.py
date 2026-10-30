"""Qdrant implementation of provider-neutral vector persistence."""

import asyncio
import logging

from qdrant_client import AsyncQdrantClient, models

from app.common.settings.qdrant import QdrantSettings
from app.repository.vector.base import VectorPoint, VectorRepositoryBase

LOGGER = logging.getLogger(__name__)


class QdrantVectorRepository(VectorRepositoryBase):
    """Validate a Qdrant collection and perform idempotent point upserts."""

    def __init__(
        self,
        client: AsyncQdrantClient,
        settings: QdrantSettings,
    ) -> None:
        self._client = client
        self._settings = settings
        self._closed = False

    async def ensure_collection(self) -> None:
        """Create the expected hybrid-ready schema or validate an existing one."""

        if not await self._client.collection_exists(self._settings.collection_name):
            if not self._settings.create_collection_if_missing:
                raise RuntimeError(
                    f"Qdrant collection {self._settings.collection_name!r} does not exist"
                )
            try:
                await self._client.create_collection(
                    collection_name=self._settings.collection_name,
                    vectors_config={
                        self._settings.dense_vector_name: models.VectorParams(
                            size=self._settings.vector_size,
                            distance=models.Distance.COSINE,
                            datatype=models.Datatype.FLOAT32,
                        )
                    },
                    sparse_vectors_config={
                        self._settings.sparse_vector_name: models.SparseVectorParams(
                            modifier=models.Modifier.IDF,
                            index=models.SparseIndexParams(on_disk=True),
                        )
                    },
                )
            except Exception:
                if not await self._client.collection_exists(
                    self._settings.collection_name
                ):
                    raise

        info = await self._client.get_collection(self._settings.collection_name)
        vectors = info.config.params.vectors
        dense = (
            vectors.get(self._settings.dense_vector_name)
            if isinstance(vectors, dict)
            else None
        )
        if dense is None:
            raise RuntimeError("Qdrant collection is missing the configured dense vector")
        if (
            dense.size != self._settings.vector_size
            or dense.distance != models.Distance.COSINE
        ):
            raise RuntimeError(
                "Qdrant dense vector schema mismatch: expected "
                f"size={self._settings.vector_size}, distance=Cosine"
            )
        sparse_vectors = info.config.params.sparse_vectors or {}
        sparse = sparse_vectors.get(self._settings.sparse_vector_name)
        if sparse is None:
            raise RuntimeError("Qdrant collection is missing the configured sparse vector")
        if sparse.modifier != models.Modifier.IDF:
            raise RuntimeError("Qdrant sparse vector must use the IDF modifier")

    async def upsert_points(self, points: tuple[VectorPoint, ...]) -> None:
        """Write points in configured batches, retrying transient provider errors."""

        for offset in range(0, len(points), self._settings.batch_size):
            batch = points[offset : offset + self._settings.batch_size]
            for point in batch:
                if len(point.dense_vector) != self._settings.vector_size:
                    raise ValueError(
                        f"point {point.point_id} has dense dimension "
                        f"{len(point.dense_vector)}; expected {self._settings.vector_size}"
                    )
            qdrant_points = [self._to_qdrant_point(point) for point in batch]
            for attempt in range(1, self._settings.max_retries + 1):
                try:
                    await self._client.upsert(
                        collection_name=self._settings.collection_name,
                        points=qdrant_points,
                        wait=True,
                    )
                    break
                except Exception:
                    if attempt == self._settings.max_retries:
                        raise
                    delay = self._settings.retry_base_seconds * (2 ** (attempt - 1))
                    LOGGER.warning(
                        "Qdrant upsert retry collection=%s attempt=%d delay=%.2f",
                        self._settings.collection_name,
                        attempt,
                        delay,
                    )
                    await asyncio.sleep(delay)

    def _to_qdrant_point(self, point: VectorPoint) -> models.PointStruct:
        vectors: dict[str, list[float] | models.SparseVector] = {
            self._settings.dense_vector_name: list(point.dense_vector)
        }
        if point.sparse_vector is not None:
            vectors[self._settings.sparse_vector_name] = models.SparseVector(
                indices=list(point.sparse_vector.indices),
                values=list(point.sparse_vector.values),
            )
        return models.PointStruct(
            id=point.point_id,
            vector=vectors,
            payload=point.payload,
        )

    async def close(self) -> None:
        """Close the injected asynchronous client exactly once."""

        if self._closed:
            return
        self._closed = True
        await self._client.close()
