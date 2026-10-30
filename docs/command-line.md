# Command line

The reusable parser is defined in `app.cli`. The `app.main` composition entry
point builds an explicit pipeline registry, and `run_job_cli` resolves the
factory selected by `--pipeline`. This keeps the entry point generic while
preventing arbitrary dynamic imports.

!!! warning

    `v1` moves claimed sources to the processing bucket, embeds text chunks,
    and upserts them to Qdrant. It changes S3 and Qdrant state.

## Arguments

| Argument | Required | Meaning |
| --- | --- | --- |
| `--pipeline` | yes | Registered indexing pipeline to execute |
| `--list-pipelines` | no | Print implemented pipelines and exit |
| `--source-bucket` | no | Bucket containing source documents; defaults from `S3_SOURCE_BUCKET` (`documents`) |
| `--object-key` | no | Index exactly one object |
| `--key-prefix` | no | Index eligible objects under a prefix |
| `--concurrency` | no | Maximum concurrent documents; default `4` |

`--object-key` and `--key-prefix` are mutually exclusive. Omitting both means
the concrete job may discover all eligible objects in the bucket.

`--source-bucket` is optional for execution and overrides the configured
default when supplied. `--pipeline` is not required with `--list-pipelines`.
List the pipelines implemented by the current image with:

```bash
python -m app.main --list-pipelines
```

The registry exposes `mock-pdf` and `v1`. The former is offline; the latter
performs conditional S3 claiming, processing movement, embedded PDF text
extraction, chunking, and remote vectorization through a pooled HTTPX client.

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

Inspect all objects within the pre-defined bucket:

```bash
python -m app.main \
  --pipeline v1 \
  --concurrency 4
```

When `--object-key` is omitted, `v1` paginates both the source selection and
matching resumable objects in `S3_PROCESSING_BUCKET`. Missing or generic MIME
values use a conservative `.pdf` extension fallback.

Source discovery precedes any embedding-service request. A nonexistent
exact key prints a concise error to stderr and returns exit status `1`; no model
artifacts are synchronized. An empty bucket or prefix returns `0` as a no-op
and also skips embedding requests. Any isolated per-object failure makes the
overall process return `1` after the remaining selected objects finish, so a
Kubernetes Job, CronJob, or Argo workflow observes the failed batch. A source is copied and verified before it
is deleted; processing objects remain durable until the future Qdrant stage.

Embedding requests are greedily batched without exceeding either
`EMBEDDING_SERVICE_MAX_BATCH_SIZE` texts or
`EMBEDDING_SERVICE_MAX_TEXT_CHARACTERS` aggregate characters. The latter must
match the embedding service's configured request limit (default `32000`).

If embedding any document fails, `v1` quarantines its verified processing copy
at `error/<original-object-key>` in the selected source bucket before deleting
the processing copy. The batch continues processing other documents and exits
with status `1`. Normal whole-bucket discovery skips `error/`; an explicit
`--key-prefix error/` can select quarantined objects when an operator intends
to retry them.

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
`build_v1_pipeline()` lazily reads settings, creates one pooled HTTPX client
using the CLI concurrency, and injects S3, embedding-service, Qdrant, and
document-indexer dependencies only when `v1` is selected. Listing
pipelines and running `mock-pdf` therefore do not require S3 credentials.

The pipeline registry chooses the top-level executable job. It does not replace
`DocumentIndexerFactory`, which selects a document indexer from normalized
content type, or capability-specific factories such as
`VectorRepositoryFactory`, which selects a registered infrastructure provider.
