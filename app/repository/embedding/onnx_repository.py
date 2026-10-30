"""ONNX Runtime embedding model adapter."""

import asyncio
import logging
from pathlib import Path
from typing import Any

from app.repository.embedding.base import EmbeddingModelRepository

LOGGER = logging.getLogger(__name__)


class OnnxEmbeddingModelRepository(EmbeddingModelRepository):
    """Load and release one ONNX model session for an indexing job.

    Inference is deliberately outside this change. Importing ``onnxruntime``
    is deferred until loading so documentation tools can inspect the module
    without initializing the native runtime.
    """

    def __init__(self) -> None:
        self._session: Any | None = None

    @property
    def is_loaded(self) -> bool:
        """Return whether an ONNX inference session exists."""

        return self._session is not None

    async def load(self, model_path: Path) -> None:
        """Load the ONNX model on a worker thread.

        Raises:
            FileNotFoundError: If the configured model artifact is absent.
            RuntimeError: If this repository already holds a session.
            Exception: Propagates ONNX Runtime model-loading failures.
        """

        if self.is_loaded:
            raise RuntimeError("embedding model is already loaded")
        if not model_path.is_file():
            raise FileNotFoundError(f"embedding model file not found: {model_path}")

        self._session = await asyncio.to_thread(self._create_session, model_path)
        LOGGER.info("loaded ONNX embedding model path=%s", model_path)

    async def close(self) -> None:
        """Release the model session; repeated calls are safe."""

        if self._session is None:
            return
        await asyncio.to_thread(self._release_session)
        LOGGER.info("embedding model repository closed")

    @staticmethod
    def _create_session(model_path: Path) -> Any:
        import onnxruntime

        return onnxruntime.InferenceSession(
            str(model_path),
            providers=["CPUExecutionProvider"],
        )

    def _release_session(self) -> None:
        self._session = None
