import unittest

from app.chunkers.pdf.v1 import PDFChunkerV1
from app.common.settings.pdf_chunking import PDFChunkingSettings
from app.common.utility.mime import normalize_content_type
from app.document_extractors.models import ExtractedPage
from app.document_indexers.factory import (
    DocumentIndexerFactory,
    UnsupportedContentTypeError,
)
from app.document_indexers.pdf import PDFDocumentIndexer
from app.repository.models import S3ObjectMetadata


class MimeAndDocumentIndexerTests(unittest.IsolatedAsyncioTestCase):
    def test_normalizes_mime_parameters_and_case(self) -> None:
        self.assertEqual(
            normalize_content_type(" Application/PDF; charset=binary ", "a"),
            "application/pdf",
        )

    def test_uses_pdf_extension_for_missing_or_generic_mime(self) -> None:
        self.assertEqual(
            normalize_content_type(None, "contracts/A.PDF"),
            "application/pdf",
        )
        self.assertEqual(
            normalize_content_type("application/octet-stream", "a.pdf"),
            "application/pdf",
        )

    def test_factory_routes_only_normalized_pdf(self) -> None:
        factory = DocumentIndexerFactory()

        indexer = factory.create("application/pdf")

        self.assertIsInstance(indexer, PDFDocumentIndexer)
        with self.assertRaisesRegex(UnsupportedContentTypeError, "text/plain"):
            factory.create("text/plain")

    async def test_pdf_chunker_returns_deterministic_citation_ready_chunks(self) -> None:
        source_metadata = S3ObjectMetadata(
            bucket="documents",
            key="contract.pdf",
            size=500,
            etag="source-etag",
            content_type="application/pdf",
        )
        processing_metadata = source_metadata.model_copy(
            update={
                "bucket": "documents-processing",
                "key": "objects/documents/contract.pdf",
            }
        )
        pages = (
            ExtractedPage(page_number=1, text="First paragraph. " * 20),
            ExtractedPage(page_number=2, text="Second page citation."),
        )
        chunker = PDFChunkerV1(
            PDFChunkingSettings(size=120, overlap=20)
        )

        first = await chunker.chunk(
            source_metadata,
            processing_metadata,
            pages,
        )
        second = await chunker.chunk(
            source_metadata,
            processing_metadata,
            pages,
        )

        self.assertEqual(first.status, "chunked")
        self.assertGreater(first.chunk_count, 2)
        self.assertEqual(first, second)
        self.assertEqual(first.chunks[0].source_bucket, "documents")
        self.assertEqual(first.chunks[0].object_key, "contract.pdf")
        self.assertEqual(first.chunks[0].page_number, 1)
        self.assertEqual(first.chunks[-1].page_number, 2)
        self.assertEqual(first.chunks[0].etag, "source-etag")
        self.assertEqual(
            first.chunks[0].processing_bucket,
            "documents-processing",
        )

    async def test_pdf_chunker_reports_empty_without_embedded_text(self) -> None:
        metadata = S3ObjectMetadata(
            bucket="documents",
            key="scan.pdf",
            size=100,
            content_type="application/pdf",
        )

        result = await PDFChunkerV1().chunk(
            metadata,
            metadata.model_copy(update={"bucket": "documents-processing"}),
            (ExtractedPage(page_number=1, text="  \n\t"),),
        )

        self.assertEqual(result.status, "empty")
        self.assertEqual(result.chunk_count, 0)
        self.assertIn("no usable embedded text", result.detail)


if __name__ == "__main__":
    unittest.main()
