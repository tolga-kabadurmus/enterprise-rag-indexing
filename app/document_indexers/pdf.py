"""PDF extraction and chunking composition."""

from app.chunkers.base import DocumentChunker
from app.document_extractors.pdf.v1 import PDFTextExtractorV1
from app.document_indexers.base import (
    DocumentIndexer,
    DocumentIndexingResult,
    LocalDocument,
)


class PDFDocumentIndexer(DocumentIndexer):
    """Coordinate text-only PDF extraction and page-bounded chunking."""

    def __init__(
        self,
        extractor: PDFTextExtractorV1,
        chunker: DocumentChunker,
    ) -> None:
        self._extractor = extractor
        self._chunker = chunker

    async def index(self, document: LocalDocument) -> DocumentIndexingResult:
        """Extract embedded PDF text and return citation-ready chunks."""

        pages = await self._extractor.extract(document.local_path)
        chunking_result = await self._chunker.chunk(
            document.source_metadata,
            document.processing_metadata,
            pages,
        )
        return DocumentIndexingResult(
            source_metadata=document.source_metadata,
            processing_metadata=document.processing_metadata,
            status=chunking_result.status,
            chunks=chunking_result.chunks,
            detail=chunking_result.detail,
        )
