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
- a runnable offline mock PDF indexing job with bounded async concurrency,
  deterministic identifiers, and structured lifecycle logging;
- a registered `v1` pipeline that conditionally claims and moves source
  objects, calls the shared embedding service through a pooled HTTPX client,
  and processes bounded selections;
- MIME normalization, `DocumentIndexerFactory`, embedded PDF text extraction,
  and citation-ready `PDFChunkerV1` output;
- stdout logging for normal processing and stderr logging for errors;
- frozen Pydantic models for validated commands, job arguments, registrations,
  and mock chunk metadata;
- a runner and factory boundary for real indexing jobs;
- a provider-neutral S3 repository contract and RustFS-compatible boto3
  adapter for bucket listing, pagination, claims, verified moves, downloads,
  and object metadata;
- grouped Pydantic settings for S3 access, embedding-service access, and model
  artifact locations;
- a `BasePipeline` startup contract that prepares the selected work before
  remote embedding requests;
- pinned libraries for RustFS/S3, PDF extraction and rendering, RapidOCR, and
  Qdrant;
- unit tests for command parsing, job cleanup, S3 behavior, factory routing,
  settings, safe download paths, claims, processing recovery, chunk identities,
  citations, and embedding-service startup order.

The registered `v1` job extracts page-bounded chunks, requests aligned dense
and token-frequency sparse vectors from the shared embedding service, and
upserts citation-ready Qdrant points. Qdrant applies IDF to the named sparse
vector so later query work can fuse lexical and semantic retrieval.

## Documentation map

- [Architecture](architecture.md) explains component boundaries and metadata.
- [Async jobs](async-jobs.md) defines lifecycle and cleanup rules.
- [S3 repository and model sync](s3-repository.md) documents implemented
  storage operations and configuration.
- [V1 pipeline](v1-pipeline.md) documents selection, routing, concurrency, and
  current result statuses.
- [Command line](command-line.md) documents object selection.
- [PDF and OCR](pdf-and-ocr.md) records the extraction and RapidOCR decisions.
- [Development](development.md) lists build, test and documentation commands.
- [API reference](api-reference.md) is generated from Python docstrings.
