from pathlib import Path
import unittest
from unittest.mock import patch

from app.document_extractors.pdf.v1 import PDFTextExtractorV1


class FakePage:
    def __init__(self, text: str | None) -> None:
        self._text = text

    def extract_text(self) -> str | None:
        return self._text


class FakeReader:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.pages = (FakePage("Page one"), FakePage(None))


class PDFTextExtractorV1Tests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_one_based_pages_and_preserves_empty_pages(self) -> None:
        with patch(
            "app.document_extractors.pdf.v1.PdfReader",
            FakeReader,
        ):
            pages = await PDFTextExtractorV1().extract(Path("contract.pdf"))

        self.assertEqual([page.page_number for page in pages], [1, 2])
        self.assertEqual(pages[0].text, "Page one")
        self.assertEqual(pages[1].text, "")


if __name__ == "__main__":
    unittest.main()
