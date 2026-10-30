"""Factory for content-type-specific document indexers."""

from collections.abc import Callable

from app.chunkers.base import DocumentChunker
from app.chunkers.pdf.v1 import PDFChunkerV1
from app.common.settings.pdf_chunking import PDFChunkingSettings
from app.common.utility.mime import PDF_CONTENT_TYPE
from app.document_extractors.pdf.v1 import PDFTextExtractorV1
from app.document_indexers.base import DocumentIndexer
from app.document_indexers.pdf import PDFDocumentIndexer


class UnsupportedContentTypeError(ValueError):
    """Raised when no document indexer is registered for a normalized MIME."""


class DocumentIndexerFactory:
    """Select document processing from an already normalized content type.

    This factory is deliberately separate from infrastructure
    ``RepositoryFactory`` and the top-level pipeline registry.
    """

    def __init__(
        self,
        pdf_chunker_factory: Callable[[], DocumentChunker] | None = None,
        pdf_extractor_factory: Callable[[], PDFTextExtractorV1] = PDFTextExtractorV1,
        pdf_chunking_settings: PDFChunkingSettings | None = None,
    ) -> None:
        settings = pdf_chunking_settings or PDFChunkingSettings()
        self._pdf_chunker_factory = pdf_chunker_factory or (
            lambda: PDFChunkerV1(settings)
        )
        self._pdf_extractor_factory = pdf_extractor_factory

    def create(self, normalized_content_type: str | None) -> DocumentIndexer:
        """Create the indexer registered for ``normalized_content_type``.

        Raises:
            UnsupportedContentTypeError: If no implementation is registered.
        """

        if normalized_content_type == PDF_CONTENT_TYPE:
            return PDFDocumentIndexer(
                self._pdf_extractor_factory(),
                self._pdf_chunker_factory(),
            )
        display_type = normalized_content_type or "unknown"
        raise UnsupportedContentTypeError(
            f"unsupported content type: {display_type}"
        )
