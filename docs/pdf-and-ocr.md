# PDF extraction and OCR

## Decision

Use `pypdf` for embedded text and RapidOCR with ONNX Runtime for scanned page
fallback. Use `pypdfium2` to render PDF pages into images accepted by RapidOCR.

The dependencies are pinned in `requirements.txt`:

- `pypdf` for page-aware embedded-text extraction;
- `pypdfium2` for permissively licensed PDF rendering;
- `rapidocr` for detection and recognition;
- `onnxruntime` as the CPU inference engine.

## Planned page flow

For each PDF page:

1. Attempt embedded-text extraction with `pypdf`.
2. Normalize the text and evaluate whether it contains meaningful content.
3. If text is absent or below the documented threshold, render the page at a
   configured resolution.
4. Run RapidOCR on the rendered image.
5. Preserve the original one-based page number and OCR confidence information.
6. Pass page text to the chunking stage without mixing page identities.

OCR should be a fallback rather than the default because rendering and model
inference are substantially more expensive than embedded-text extraction.

## Operational constraints

RapidOCR inference and PDF rendering are blocking/CPU-intensive. Execute them
outside the event loop and enforce the job concurrency limit. Initialize models
once per worker where safe rather than once per page. Do not log page images or
full OCR text by default.

The first implementation should make the OCR threshold, rendering resolution,
language/model route and minimum confidence configurable through validated
environment variables. Accuracy must be checked with representative enterprise
documents before changing model size or adding GPU support.
