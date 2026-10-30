# Command line

The reusable parser is defined in `app.cli`. The `app.main` composition entry
point builds an explicit pipeline registry, and `run_job_cli` resolves the
factory selected by `--pipeline`. This keeps the entry point generic while
preventing arbitrary dynamic imports.

!!! warning

    `v1` moves claimed sources to the processing bucket and returns text
    chunks, but it does not yet generate embeddings or Qdrant points.

## Arguments

| Argument | Required | Meaning |
| --- | --- | --- |
| `--pipeline` | yes | Registered indexing pipeline to execute |
| `--list-pipelines` | no | Print implemented pipelines and exit |
| `--source-bucket` | yes | Bucket containing source documents |
| `--object-key` | no | Index exactly one object |
| `--key-prefix` | no | Index eligible objects under a prefix |
| `--concurrency` | no | Maximum concurrent documents; default `4` |

`--object-key` and `--key-prefix` are mutually exclusive. Omitting both means
the concrete job may discover all eligible objects in the bucket.

`--pipeline` and `--source-bucket` are not required with `--list-pipelines`.
List the pipelines implemented by the current image with:

```bash
python -m app.main --list-pipelines
```

The registry exposes `mock-pdf` and `v1`. The former is offline; the latter
performs conditional S3 claiming, processing movement, model initialization,
embedded PDF text extraction, and chunking.

## Selection examples

Inspect one exact object:

```bash
python -m app.main \
  --pipeline v1 \
  --source-bucket documents \
  --object-key contracts/contract.pdf \
  --concurrency 2
```

Inspect all objects in a bucket:

```bash
python -m app.main \
  --pipeline v1 \
  --source-bucket documents \
  --concurrency 4
```

Inspect a prefix:

```bash
python -m app.main \
  --pipeline v1 \
  --source-bucket documents \
  --key-prefix contracts/2026/ \
  --concurrency 4
```

When `--object-key` is omitted, `v1` paginates both the source selection and
matching resumable objects in `S3_PROCESSING_BUCKET`. Missing or generic MIME
values use a conservative `.pdf` extension fallback.

Source discovery precedes embedding-model download and loading. A nonexistent
exact key prints a concise error to stderr and returns exit status `1`; no model
artifacts are synchronized. An empty bucket or prefix returns `0` as a no-op
and also skips model initialization. A source is copied and verified before it
is deleted; processing objects remain durable until the future Qdrant stage.

## Docker Compose

From the orchestration repository, run `v1` as a one-shot job independently of
the development container's sleeping command:

```bash
docker compose --profile dev run --rm enterprise-rag-indexing \
  python -m app.main \
  --pipeline v1 \
  --source-bucket documents \
  --key-prefix contracts/2026/ \
  --concurrency 4
```

## Composition

Each registered factory receives the same `IndexingJobArguments`.
`build_v1_pipeline()` lazily reads settings and injects S3, embedding runtime,
and document-indexer dependencies only when `v1` is selected. Listing
pipelines and running `mock-pdf` therefore do not require S3 credentials.

The pipeline registry chooses the top-level executable job. It does not replace
`DocumentIndexerFactory`, which selects a document indexer from normalized
content type, or `RepositoryFactory`, which selects infrastructure
implementations.
