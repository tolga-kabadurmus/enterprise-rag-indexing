import unittest

from app.chunkers.pdf.v1 import PDFChunkerV1
from app.common.utility.mime import normalize_content_type
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

    async def test_pdf_chunker_v1_reports_truthful_incomplete_status(self) -> None:
        metadata = S3ObjectMetadata(
            bucket="documents",
            key="contract.pdf",
            size=100,
            content_type="application/pdf",
        )

        result = await PDFChunkerV1().chunk(metadata)

        self.assertEqual(result.status, "not_implemented")
        self.assertEqual(result.chunk_count, 0)
        self.assertIn("not implemented", result.detail)


if __name__ == "__main__":
    unittest.main()
