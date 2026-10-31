# PDF extraction and OCR

## Implemented text-only flow

`PDFTextExtractorV1` opens the temporary local PDF with `pypdf` and returns one
`ExtractedPage` per original page. Extraction runs through
`asyncio.to_thread()` because PDF parsing is blocking. One-based page numbers
are preserved through `PDFChunkerV1`, so every chunk has an unambiguous citation.

`PDFChunkerV1` normalizes embedded text and creates overlapping character
windows without crossing page boundaries. It prefers paragraph or whitespace
boundaries and falls back to a hard maximum for unusually long text.

## Explicit limitations

- No OCR is executed.
- Images and scanned-only pages produce no text.
- Visual layout is not reconstructed.
- Tables are not identified or structurally represented.
- If `pypdf` extracts table-cell text, it is chunked as ordinary text; reliably
  excluding it requires a future layout/table detector.
- Encrypted or malformed PDFs may fail extraction and are reported per object.

RapidOCR and `pypdfium2` remain installed for a later OCR fallback, but their
presence must not be interpreted as implemented OCR behavior.

## Planned OCR fallback

A later version may render pages without useful embedded text and send them to
RapidOCR. That change must preserve the original page number, expose confidence
and language settings through validated configuration, run blocking work
outside the event loop, and include dedicated accuracy tests.
