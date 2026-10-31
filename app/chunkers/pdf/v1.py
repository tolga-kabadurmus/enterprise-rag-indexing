"""Version-one deterministic PDF text chunking."""

import re
from uuid import NAMESPACE_URL, uuid5

from app.chunkers.base import ChunkingResult, DocumentChunk, DocumentChunker
from app.common.settings.pdf_chunking import PDFChunkingSettings
from app.document_extractors.models import ExtractedPage
from app.repository.models import S3ObjectMetadata


class PDFChunkerV1(DocumentChunker):
    """Split embedded PDF page text into citation-ready character windows.

    This implementation intentionally handles text only. It does not run OCR,
    interpret images, reconstruct visual layout, or preserve table structure.
    ``pypdf`` may expose text contained in table cells; that text is chunked as
    ordinary text because reliable table exclusion requires layout detection.
    Chunks never cross a page boundary, so every result has one unambiguous
    one-based PDF page citation.
    """

    def __init__(self, settings: PDFChunkingSettings | None = None) -> None:
        self._settings = settings or PDFChunkingSettings()

    async def chunk(
        self,
        source_metadata: S3ObjectMetadata,
        processing_metadata: S3ObjectMetadata,
        pages: tuple[ExtractedPage, ...],
    ) -> ChunkingResult:
        """Create deterministic page-bounded chunks from extracted text."""

        document_id = str(
            uuid5(
                NAMESPACE_URL,
                f"s3://{source_metadata.bucket}/{source_metadata.key}",
            )
        )
        chunks: list[DocumentChunk] = []
        for page in pages:
            normalized_text = self._normalize_text(page.text)
            for page_chunk_index, (start, end, text) in enumerate(
                self._split_text(normalized_text)
            ):
                chunk_index = len(chunks)
                chunk_id = str(
                    uuid5(
                        NAMESPACE_URL,
                        f"{document_id}:page={page.page_number}:"
                        f"chunk={page_chunk_index}",
                    )
                )
                chunks.append(
                    DocumentChunk(
                        document_id=document_id,
                        chunk_id=chunk_id,
                        text=text,
                        source_bucket=source_metadata.bucket,
                        object_key=source_metadata.key,
                        page_number=page.page_number,
                        chunk_index=chunk_index,
                        page_chunk_index=page_chunk_index,
                        character_start=start,
                        character_end=end,
                        content_type=source_metadata.content_type,
                        etag=source_metadata.etag,
                        processing_bucket=processing_metadata.bucket,
                        processing_object_key=processing_metadata.key,
                    )
                )

        if not chunks:
            return ChunkingResult(
                status="empty",
                detail="PDF contains no usable embedded text",
            )
        return ChunkingResult(
            status="chunked",
            chunks=tuple(chunks),
            detail=f"created {len(chunks)} page-bounded text chunks",
        )

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized_lines = [
            re.sub(r"[ \t\f\v]+", " ", line).strip()
            for line in text.replace("\r\n", "\n")
            .replace("\r", "\n")
            .split("\n")
        ]
        paragraphs: list[str] = []
        current: list[str] = []
        for line in normalized_lines:
            if line:
                current.append(line)
            elif current:
                paragraphs.append(" ".join(current))
                current = []
        if current:
            paragraphs.append(" ".join(current))
        return "\n\n".join(paragraphs).strip()

    def _split_text(self, text: str) -> tuple[tuple[int, int, str], ...]:
        if not text:
            return ()
        size = self._settings.size
        overlap = self._settings.overlap
        pieces: list[tuple[int, int, str]] = []
        start = 0
        while start < len(text):
            maximum_end = min(start + size, len(text))
            end = maximum_end
            if maximum_end < len(text):
                minimum_boundary = start + max(size // 2, 1)
                paragraph_boundary = text.rfind(
                    "\n\n",
                    minimum_boundary,
                    maximum_end,
                )
                whitespace_boundary = text.rfind(
                    " ",
                    minimum_boundary,
                    maximum_end,
                )
                boundary = max(paragraph_boundary, whitespace_boundary)
                if boundary > start:
                    end = boundary
            actual_start = start
            while actual_start < end and text[actual_start].isspace():
                actual_start += 1
            actual_end = end
            while actual_end > actual_start and text[actual_end - 1].isspace():
                actual_end -= 1
            if actual_start < actual_end:
                pieces.append(
                    (
                        actual_start,
                        actual_end,
                        text[actual_start:actual_end],
                    )
                )
            if end >= len(text):
                break
            next_start = max(end - overlap, start + 1)
            while next_start < len(text) and text[next_start].isspace():
                next_start += 1
            start = next_start
        return tuple(pieces)
