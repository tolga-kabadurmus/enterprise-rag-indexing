# Enterprise RAG indexing

`enterprise-rag-indexing` is the disposable, asynchronous ingestion component
of Enterprise RAG. A job selects PDF objects from an S3-compatible source,
extracts text (using OCR when needed), creates chunks and embeddings, and
upserts vectors with source metadata into Qdrant.

## Current implementation status

The repository currently provides:

- a validated command-line contract for bucket, exact-key and prefix selection;
- an asynchronous job lifecycle with cleanup after initialization or execution
  failures;
- a runnable mock PDF indexing job with bounded async concurrency,
  deterministic identifiers, and structured lifecycle logging;
- an explicit pipeline registry and required `--pipeline` CLI selection;
- a runner and factory boundary for real indexing jobs;
- pinned libraries for RustFS/S3, PDF extraction and rendering, RapidOCR, and
  Qdrant;
- unit tests for command parsing and job cleanup.

The runnable job is explicitly a mock: it does not read RustFS objects or write
Qdrant points. Concrete PDF extraction, OCR, chunking, embedding and
persistence stages are not implemented yet. The pages in this site clearly
distinguish the current contracts from the planned pipeline.

## Documentation map

- [Architecture](architecture.md) explains component boundaries and metadata.
- [Async jobs](async-jobs.md) defines lifecycle and cleanup rules.
- [Command line](command-line.md) documents object selection.
- [PDF and OCR](pdf-and-ocr.md) records the extraction and RapidOCR decisions.
- [Development](development.md) lists build, test and documentation commands.
- [API reference](api-reference.md) is generated from Python docstrings.
