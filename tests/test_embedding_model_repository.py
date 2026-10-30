import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.repository.embedding.onnx_repository import OnnxEmbeddingModelRepository


class OnnxEmbeddingModelRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_loads_once_and_closes_idempotently(self) -> None:
        repository = OnnxEmbeddingModelRepository()
        with tempfile.TemporaryDirectory() as directory:
            model_path = Path(directory) / "model.onnx"
            model_path.write_bytes(b"model")
            with patch.object(
                repository,
                "_create_session",
                return_value=object(),
            ) as create_session:
                await repository.load(model_path)

            self.assertTrue(repository.is_loaded)
            create_session.assert_called_once_with(model_path)
            with self.assertRaisesRegex(RuntimeError, "already loaded"):
                await repository.load(model_path)

        await repository.close()
        await repository.close()
        self.assertFalse(repository.is_loaded)

    async def test_rejects_missing_model_file(self) -> None:
        repository = OnnxEmbeddingModelRepository()

        with self.assertRaisesRegex(FileNotFoundError, "model file not found"):
            await repository.load(Path("/missing/model.onnx"))


if __name__ == "__main__":
    unittest.main()
