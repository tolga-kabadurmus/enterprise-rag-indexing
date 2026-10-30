# Enterprise RAG — Indexing

`enterprise-rag-indexing` is the document ingestion and indexing component of the Enterprise RAG prototype. It runs as a **one-shot, asynchronous job**: read eligible documents from RustFS through its S3-compatible API, extract their text, split it into chunks, request embeddings from `enterprise-rag-embedding-service`, and later write vectors with source metadata to Qdrant.

For project-wide architecture and coding conventions, see the root [`AGENTS.md`](https://github.com/tolga-kabadurmus/enterprise-rag/blob/main/AGENTS.md) in the orchestration repository. The URL assumes that repository is created under the indicated GitHub account.

## Documentation

The full developer documentation starts at [`docs/index.md`](docs/index.md) and is configured by `mkdocs.yml`. It covers architecture, asynchronous job lifecycle, CLI arguments, PDF/RapidOCR decisions, development commands, and an API reference generated from Python docstrings.

```bash
python3 -m virtualenv venv
venv/bin/python -m pip install -r requirements-docs.txt
venv/bin/mkdocs serve
venv/bin/mkdocs build --strict
```

## Responsibilities

- Discover eligible objects from a specified S3 bucket and optional key prefix.
- Handle **PDF documents first**, with a document-indexer factory designed to support other content types later.
- Extract text and page information, chunk the text, and generate embeddings.
- Upsert vectors and source metadata to Qdrant so the query service can cite the originating document.
- Run document processing concurrently using `asyncio` with an explicit concurrency limit.
- Move or transition documents through a staging/processing workflow while guarding against duplicate indexing.
- Log processing outcomes, handle per-document errors, and release external resources on exit.

## Implemented infrastructure boundary

The project now includes a provider-neutral `S3Repository` contract and a
RustFS-compatible boto3 implementation. It supports accessible-bucket listing,
paginated object listing, exact object downloads, prefix downloads, and
`head_object` metadata. Blocking boto3 calls run through a bounded
`asyncio.to_thread()` boundary, and the client is closed through the async job
lifecycle.

`BasePipeline` is the ancestor for real/versioned pipelines. The registered
`v1` pipeline first discovers an exact object or every selected bucket object.
After successful discovery it uses a shared, pooled HTTPX client to call the
embedding service. Before processing it uses
a conditional claim, copies selected objects into the configurable processing
bucket, verifies the durable copy, and only then deletes the source object.
Claim release verifies its owner and ETag so an older attempt cannot delete a
new owner's marker.
`DocumentIndexerFactory` routes PDFs through `PDFTextExtractorV1` and
`PDFChunkerV1`.

`PDFChunkerV1` returns page-bounded text chunks with deterministic document and
chunk IDs plus source metadata used in Qdrant payloads. V1
requests one vector per chunk from the shared embedding service and upserts it
to Qdrant with deterministic IDs and citation payloads.
Processing objects are therefore retained. The registered `mock-pdf` job remains
side-effect-free.

## Conceptual processing flow

```text
RustFS source bucket (+ optional prefix)
            |
            v
    Object discovery / claim
            |
            v
  DocumentIndexerFactory
      (PDF initially)
            |
            v
     Text extraction
            |
            v
      Document chunks
            |
            v
   Embedding service (pooled HTTPX)
            |
            v
 Qdrant vectors + metadata
            |
            v
 Processing result / staging state
```

## Architectural conventions

- Python 3.12.3 on Ubuntu 24.04.4 LTS is the primary development target.
- Use Clean Architecture with repositories for infrastructure access, use cases for individual application operations, and a controller when several use cases need orchestration.
- Inject repository dependencies through constructors. Use `RepositoryFactory` for provider-specific infrastructure adapters and `DocumentIndexerFactory` for document content-type selection.
- Implement indexing resources as an **asynchronous context manager**: `__aenter__()` acquires/initializes them and `__aexit__()` closes/disposes of them.
- Keep extraction, chunking, embedding, and vector persistence as separate concerns.
- Keep code straightforward and readable; avoid unnecessary frameworks or abstractions.

Conceptual lifecycle (not yet an implemented public API):

```python
async with PDFDocumentIndexing(...) as indexer:
    await indexer.run()
```

## Document identity and reliability

At minimum, indexed chunks should retain the source bucket, object key, document ID, chunk ID, and page number when available. The indexing and query services must use compatible embedding models and vector dimensions.

Moving an object in S3-compatible storage is generally a **copy followed by
delete**, not an atomic lock. V1 first creates an `If-None-Match: *` claim marker
in the processing bucket. Only the winner may move and process that source
identity. Stale claims may be reclaimed after the configured TTL. Source
deletion occurs only after the processing copy is verified by size. A process
crash can leave a claim until its TTL expires; this is a lease-style prototype,
not a transactional workflow engine.

## Configuration

The root orchestration repository owns all environment files. Copy
`dev-envs/enterprise-rag-indexing.env.example` to the Git-ignored
`dev-envs/enterprise-rag-indexing.env`, then make its S3 credentials match the
RustFS service credentials. Compose injects that file only into the indexing
service.

| Variable | Default/example | Purpose |
| --- | --- | --- |
| `S3_PROVIDER` | `rustfs` | Infrastructure provider selected by `RepositoryFactory` |
| `S3_ENDPOINT_URL` | `http://rustfs:9000` | Container-network S3 endpoint |
| `S3_ACCESS_KEY` | required | RustFS access key |
| `S3_SECRET_KEY` | required | RustFS secret key |
| `S3_REGION` | `us-east-1` | S3 signing region |
| `S3_ADDRESSING_STYLE` | `path` | boto3 addressing style |
| `S3_VERIFY_TLS` | `false` locally | TLS certificate verification |
| `S3_MAX_CONCURRENCY` | `4` | Maximum simultaneous blocking boto3 calls |
| `S3_PROCESSING_BUCKET` | `documents-processing` | Durable in-progress objects and conditional claims |
| `S3_CLAIM_TTL_SECONDS` | `3600` | Age after which an abandoned claim may be reclaimed |
| `S3_SOURCE_BUCKET` | `documents` | Default source bucket when `--source-bucket` is omitted |
| `INDEXING_WORK_DIRECTORY` | `/work/indexing` | Ephemeral local PDF workspace |
| `PDF_CHUNK_SIZE` | `1200` | Maximum normalized characters per chunk |
| `PDF_CHUNK_OVERLAP` | `200` | Character overlap between adjacent page chunks |
| `EMBEDDING_SERVICE_PROVIDER` | `httpx` | Provider selected by `RepositoryFactory` |
| `EMBEDDING_SERVICE_URL` | `http://enterprise-rag-embedding-service:8081` | Shared embedding API base URL |
| `EMBEDDING_SERVICE_API_PATH` | `/v1/embeddings` | Embedding API path |
| `EMBEDDING_SERVICE_TIMEOUT_SECONDS` | `60` | Per-request HTTP timeout |
| `EMBEDDING_SERVICE_VERIFY_TLS` | `false` locally | TLS certificate verification |
| `EMBEDDING_SERVICE_MAX_CONNECTIONS` | `4` | Upper bound for the HTTP pool |
| `EMBEDDING_SERVICE_MAX_KEEPALIVE_CONNECTIONS` | `4` | Keep-alive connections in the HTTP pool |
| `EMBEDDING_SERVICE_MAX_BATCH_SIZE` | `32` | Chunk texts per embedding request |
| `EMBEDDING_SERVICE_MAX_TEXT_CHARACTERS` | `32000` | Aggregate text characters per embedding request |
| `EMBEDDING_SERVICE_EXPECTED_MODEL` | `intfloat/multilingual-e5-small` | Response model validation |
| `EMBEDDING_SERVICE_EXPECTED_DIMENSION` | `384` | Response vector dimension validation |
| `QDRANT_URL` | `http://qdrant:6333` | Qdrant endpoint |
| `QDRANT_COLLECTION_NAME` | `enterprise_rag_chunks` | Chunk collection |
| `QDRANT_DENSE_VECTOR_NAME` | `dense` | Dense named vector |
| `QDRANT_SPARSE_VECTOR_NAME` | `sparse` | Reserved sparse named vector |
| `QDRANT_VECTOR_SIZE` | `384` | Dense vector dimension |
| `QDRANT_BATCH_SIZE` | `64` | Points per upsert |

The S3, model-artifact, embedding-service, workspace, and PDF chunking groups use separate Pydantic
`BaseSettings` classes under `app/common/settings`. Never log credentials.

The source-document bucket and optional key prefix are **runtime CLI
arguments**. `--source-bucket` overrides `S3_SOURCE_BUCKET`; when the
argument is omitted, the configured `documents` default is used. The embedding-service endpoint,
pool limits, and response contract are application environment settings.

## Running with Docker Compose

This module is a Git submodule of the top-level [`enterprise-rag`](https://github.com/tolga-kabadurmus/enterprise-rag) repository, where `docker-compose.yaml` is defined. From that repository root, after starting RustFS and Qdrant:

```bash
docker compose --profile dev up -d rustfs qdrant
docker compose --profile dev run --rm enterprise-rag-indexing \
  python -m app.main \
  --pipeline v1 \
  --source-bucket documents \
  --key-prefix contracts/2026/
```

Omit both `--object-key` and `--key-prefix` to process every source or resumable
processing object in the selection. `v1` creates citation-ready chunks and
requests their vectors from the embedding service in bounded batches, then
upserts citation-ready Qdrant points. Use `python -m app.main --list-pipelines` to see
registered workflows. `mock-pdf` remains available for a fully offline
lifecycle check. The Dockerfile uses `dumb-init` as its entrypoint/PID 1
mechanism, and the development service bind-mounts the local `app` package.

A missing exact `--object-key` is reported as a concise repository-level error
and exits with status `1`, allowing Kubernetes or Argo to mark the run failed.
Any per-object processing failure also produces exit status `1` after the
remaining selected objects complete.
When remote embedding fails, `v1` copies the durable processing object to
`error/<original-object-key>` in the selected source bucket, verifies its size,
and only then deletes the processing copy. Unprefixed bucket discovery skips
the `error/` quarantine; operators may select that prefix explicitly.
An empty bucket/prefix selection is a successful no-op and skips embedding and
Qdrant requests. Cleanup closes Qdrant, HTTPX, and S3 clients, including after
failures.

Check the root project's README for cloning submodules and stopping the stack. This indexing container is a disposable job; it should not run as a persistent daemon.

## Local development

```bash
python3 -m virtualenv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Keep dependency specifications in this repository's own `requirements.txt` and its Dockerfile under `Dockerfiles/`.

## Testing and documentation

Use unit tests for chunking, metadata, factories, use cases, and controllers, with mocked/fake repositories. Validate real RustFS and Qdrant interaction in separate integration tests. Record successful/failed object counts, chunk counts, and durations without logging secrets or full document text. Validate documentation with `mkdocs build --strict`.

## Scope

**Initial target:** PDF indexing into Qdrant with traceable source metadata and basic logging/error handling. Other document formats, advanced orchestration, CI/CD, Kubernetes/OpenShift Helm charts, and observability dashboards are potential extensions, not implemented features.

The current `v1` implementation ends after remote vector generation in memory;
it must not be described as a complete Qdrant indexing pipeline.
