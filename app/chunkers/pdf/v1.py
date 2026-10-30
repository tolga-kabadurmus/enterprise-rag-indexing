"""Version-one PDF chunking component shell."""

from app.chunkers.base import ChunkingResult, DocumentChunker
from app.repository.models import S3ObjectMetadata


class PDFChunkerV1(DocumentChunker):
    """Reserve the v1 PDF chunking boundary for incremental implementation.

    The current implementation intentionally produces no document text,
    chunks, embeddings, or persistence claims. Its explicit status prevents
    metadata-only processing from being mistaken for successful indexing.
    """

    async def chunk(self, metadata: S3ObjectMetadata) -> ChunkingResult:
        """Return the current not-yet-implemented PDF chunking status."""

        return ChunkingResult(
            status="not_implemented",
            chunk_count=0,
            detail=(
                "PDFChunkerV1 is selected, but PDF extraction and chunking "
                "are not implemented yet"
            ),
        )
