"""Text-only PDF extraction using pypdf."""

import asyncio
from pathlib import Path

from pypdf import PdfReader

from app.document_extractors.models import ExtractedPage


class PDFTextExtractorV1:
    """Extract embedded page text without OCR, images, or layout analysis."""

    async def extract(self, pdf_path: Path) -> tuple[ExtractedPage, ...]:
        """Extract embedded text from ``pdf_path`` outside the event loop.

        Args:
            pdf_path: Existing local PDF downloaded by the pipeline.

        Returns:
            One validated record per PDF page, including pages with no text.

        Raises:
            FileNotFoundError: If the local PDF is missing.
            pypdf.errors.PdfReadError: If the PDF cannot be parsed.
        """

        return await asyncio.to_thread(self._extract_sync, pdf_path)

    @staticmethod
    def _extract_sync(pdf_path: Path) -> tuple[ExtractedPage, ...]:
        reader = PdfReader(pdf_path)
        return tuple(
            ExtractedPage(
                page_number=page_number,
                text=page.extract_text() or "",
            )
            for page_number, page in enumerate(reader.pages, start=1)
        )
