"""PDF document indexer composition."""

from app.chunkers.base import DocumentChunker
from app.document_indexers.base import DocumentIndexer, DocumentIndexingResult
from app.repository.models import S3ObjectMetadata


class PDFDocumentIndexer(DocumentIndexer):
    """Coordinate the configured PDF chunker for one PDF object."""

    def __init__(self, chunker: DocumentChunker) -> None:
        self._chunker = chunker

    async def index(
        self,
        metadata: S3ObjectMetadata,
    ) -> DocumentIndexingResult:
        """Delegate PDF processing to the injected versioned chunker."""

        chunking_result = await self._chunker.chunk(metadata)
        return DocumentIndexingResult(
            metadata=metadata,
            status=chunking_result.status,
            chunk_count=chunking_result.chunk_count,
            detail=chunking_result.detail,
        )
