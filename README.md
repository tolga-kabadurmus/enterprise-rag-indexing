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

Use environment variables and an untracked local `.env` file for the S3 endpoint and credentials, Qdrant connection, embedding provider/model, concurrency, and any staging configuration. Supply `.env.example` without secrets. Exact environment-variable names will be documented when the configuration schema is implemented.

The source bucket and optional key prefix are **runtime CLI arguments** rather than hard-coded settings. Any staging bucket argument or setting must also be documented in the implementation.

## Running with Docker Compose

This module is a Git submodule of the top-level [`enterprise-rag`](https://github.com/tolga-kabadurmus/enterprise-rag) repository, where `docker-compose.yaml` is defined. From that repository root, after starting RustFS and Qdrant:

```bash
docker compose --profile dev up -d rustfs qdrant
docker compose run --rm enterprise-rag-indexing --source-bucket documents --key-prefix ""
```

**Planned command, not yet verified:** The example assumes a Compose service called `enterprise-rag-indexing` whose image entrypoint forwards the flags to the indexing CLI. The final implementation must make its argument names and staging configuration consistent with this README. The Dockerfile must use `dumb-init` as its entrypoint/PID 1 mechanism. A development bind mount of this repository's source code is expected in the root Compose file.

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

This README describes the **intended design**, not a claim that its code, CLI flags, Docker image, or services already exist. Update commands and configuration details when they are implemented.
