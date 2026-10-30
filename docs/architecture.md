# Architecture

## Pipeline boundary

The indexing application is a one-shot job, not a long-running worker. A
single invocation processes the requested bucket selection, reports outcomes,
closes resources and exits.

```text
CLI selection
    |
    v
V1IndexingPipeline(BasePipeline)
    |
    +--> S3 repository ----------> selection + complete metadata
    +--> embedding repository ---> one loaded ONNX session
    +--> DocumentIndexerFactory -> normalized MIME routing
    +--> PDFDocumentIndexer -----> PDFChunkerV1
                                      |
                                      +--> not_implemented (current boundary)
```

The CLI, job contract, runner, side-effect-free mock, S3 repository, repository
factory, model synchronization base pipeline, and `v1` metadata-routing job
exist today. PDF extraction, chunk creation, embedding inference, and Qdrant
persistence remain planned.

## Implemented repository layout

```text
app/
├── chunkers/           # PDFChunkerV1 and chunking result contract
├── common/
│   ├── settings/       # S3Settings and EmbeddingModelSettings
│   └── utility/        # safe object-key-to-path conversion
├── document_indexers/  # MIME-selected document processing boundary
├── jobs/               # v1 and offline mock top-level jobs
├── pipelines/          # BasePipeline startup/cleanup contract
└── repository/
    ├── base.py         # shared repository lifecycle
    ├── factory.py      # infrastructure provider selection
    ├── models.py       # Pydantic bucket/object records
    ├── embedding/      # ONNX model runtime lifecycle
    └── s3/             # S3 contract and boto3 implementation
```

## Pipeline selection

`IndexingPipelineRegistry` maps stable CLI names to factories that construct
`AsyncIndexingJob` implementations. `app.main` owns the explicit registrations;
the shared CLI resolves `--pipeline` and passes the remaining validated job
arguments to the selected factory. Only executable pipelines are registered.

This top-level registry answers "which job should run?" It remains separate
from `DocumentIndexerFactory`, which answers "how should this content type be
indexed?", and `RepositoryFactory`, which answers "which infrastructure
provider should be used?"

## Validated data models

Command inputs, job arguments, pipeline registrations, and chunk metadata use
frozen Pydantic `BaseModel` classes. Pydantic performs boundary validation,
rejects unknown fields, and provides predictable serialization without making
behavior-oriented jobs or registries inherit from a data-model base class.

Environment-backed application configuration must use
`pydantic-settings.BaseSettings`. Direct environment access belongs in a
settings composition boundary rather than repositories, use cases, or jobs.

## Clean Architecture placement

Repositories own external access to RustFS/S3, embedding providers and Qdrant.
Use cases own one application operation and normally depend on one repository.
A controller coordinates multiple use cases for the full document pipeline.
The composition layer creates repositories, use cases, the controller and the
concrete job; business methods must not construct infrastructure clients.

`RepositoryFactory` creates the RustFS-compatible S3 adapter and ONNX model
runtime. `DocumentIndexerFactory` separately selects a document implementation
from normalized content type. It maps `application/pdf` to a
`PDFDocumentIndexer` composed with `PDFChunkerV1`; unsupported types are
reported and skipped per object.

## Source metadata

Every stored chunk must retain at least:

| Field | Purpose |
| --- | --- |
| `source_bucket` | RustFS/S3 bucket used for retrieval and citation |
| `object_key` | Original object location within the bucket |
| `document_id` | Deterministic identity for retries |
| `chunk_id` | Deterministic vector point identity |
| `page_number` | Original PDF page when known |

Additional useful metadata includes content type, checksum, chunk ordinal,
embedding model and indexing timestamp. Do not store secrets or log complete
document contents.

## Retry and overlap rules

S3 object movement is normally copy-then-delete and is not an atomic lock.
Deterministic IDs and Qdrant upserts make retrying safe, but they do not prevent
two overlapping jobs from doing duplicate work. Until a complete claim system
exists, do not run overlapping jobs against the same bucket and key range.
Never delete the only durable source after a partial failure.
