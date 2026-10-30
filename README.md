# Enterprise RAG — Indexing

`enterprise-rag-indexing` is the document ingestion and indexing component of the Enterprise RAG prototype. It runs as a **one-shot, asynchronous job**: read eligible documents from RustFS through its S3-compatible API, extract their text, split it into chunks, generate embeddings, and write vectors with source metadata to Qdrant.

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
Only after successful, non-empty discovery does it download the configured
embedding artifacts and load the ONNX model once. It then resolves complete S3
metadata and processes objects concurrently in bounded batches.
`DocumentIndexerFactory` currently routes PDFs to `PDFChunkerV1`.

`PDFChunkerV1` deliberately returns `not_implemented`: PDF extraction,
chunk creation, embedding inference, and Qdrant persistence remain later
steps. The registered `mock-pdf` job remains side-effect-free and does not
contact RustFS.

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
   Embedding generation
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

Moving an object in S3-compatible storage is generally a **copy followed by delete**, not an atomic lock. Staging alone does not prevent simultaneous jobs from processing the same input. Use a documented claim/processing state, deterministic document/chunk identifiers, and idempotent Qdrant upserts; until cross-job claiming is implemented, avoid overlapping indexing runs on the same inputs. Do not delete the only durable source copy following a partial failure.

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
| `EMBEDDINGS_BUCKET` | `models` | Bucket containing model artifacts |
| `EMBEDDINGS_KEY_PREFIX` | `embeddings` | Model artifact key prefix |
| `EMBEDDINGS_LOCAL_DIRECTORY` | `/models/embeddings` | Volume-backed local model directory |
| `EMBEDDINGS_RUNTIME` | `onnx` | Model runtime created by `RepositoryFactory` |
| `EMBEDDINGS_MODEL_FILE` | `onnx/model.onnx` | Model artifact relative to the local directory |

`S3Settings` and `EmbeddingModelSettings` are separate Pydantic
`BaseSettings` classes under `app/common/settings`. Never log credentials.

The source-document bucket and optional key prefix are **runtime CLI
arguments** rather than hard-coded settings. The embedding-model bucket and
prefix are application environment settings because every real pipeline needs
them during startup.

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

Omit both `--object-key` and `--key-prefix` to inspect every object in the
source bucket. `v1` logs metadata and truthful per-object statuses but does not
yet create chunks or vectors. Use `python -m app.main --list-pipelines` to see
registered workflows. `mock-pdf` remains available for a fully offline
lifecycle check. The Dockerfile uses `dumb-init` as its entrypoint/PID 1
mechanism, and the development service bind-mounts the local `app` package.

A missing exact `--object-key` is reported as a concise repository-level error
and exits with status `1`, allowing Kubernetes or Argo to mark the run failed.
An empty bucket/prefix selection is a successful no-op and skips model download
and loading.

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

The current `v1` implementation ends after metadata routing and the explicit
`PDFChunkerV1` placeholder result. It must not be described as a complete PDF
indexing or embedding pipeline.
