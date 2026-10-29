# Command line

The reusable parser is defined in `app.cli`. The `app.main` composition entry
point builds an explicit pipeline registry, and `run_job_cli` resolves the
factory selected by `--pipeline`. This keeps the entry point generic while
preventing arbitrary dynamic imports.

!!! warning

    The current command runs a mock. It does not list or download RustFS
    objects, extract PDF content, generate embeddings, or update Qdrant.

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

The initial registry exposes only `mock-pdf`. A real pipeline must not be
listed until its complete composition is implemented.

## Selection examples

Index one object:

```bash
python -m app.main \
  --pipeline mock-pdf \
  --source-bucket documents \
  --object-key contracts/contract.pdf \
  --concurrency 2
```

Index a prefix:

```bash
python -m app.main \
  --pipeline mock-pdf \
  --source-bucket documents \
  --key-prefix contracts/2026/ \
  --concurrency 4
```

The prefix example simulates one object named
`contracts/2026/mock-document.pdf`. The log output includes its deterministic
document and chunk IDs.

## Docker Compose

From the orchestration repository, run the one-shot mock independently of the
development container's sleeping command:

```bash
docker compose --profile dev run --rm enterprise-rag-indexing \
  python -m app.main \
  --pipeline mock-pdf \
  --source-bucket documents \
  --key-prefix contracts/2026/ \
  --concurrency 4
```

## Composition

The current entry point intentionally remains small:

```python
from app.jobs.registry import (
    IndexingPipelineRegistration,
    IndexingPipelineRegistry,
)
from app.jobs.mock import MockPDFDocumentIndexing


registry = IndexingPipelineRegistry(
    registrations=(
        IndexingPipelineRegistration(
            name="mock-pdf",
            description="Simulate PDF indexing without external writes",
            job_factory=MockPDFDocumentIndexing,
        ),
    )
)
```

Each factory receives the same `IndexingJobArguments`. To add a pipeline,
implement `AsyncIndexingJob`, compose its dependencies in `app.main`, and add
one explicit registration. Provider clients belong in this composition layer
and must be injected into the concrete job or its controller.

The pipeline registry chooses the top-level executable job. It does not replace
`DocumentIndexerFactory`, which will select a document indexer from validated
content type inside the real pipeline, or `RepositoryFactory`, which selects
infrastructure implementations.
