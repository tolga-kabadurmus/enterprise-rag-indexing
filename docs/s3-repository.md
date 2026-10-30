# S3 repository and model synchronization

## Implemented operations

`S3Repository` is the provider-neutral storage contract. The current
`Boto3S3Repository` implementation is configured for RustFS and provides:

- accessible bucket listing;
- complete, paginated `list_objects_v2` discovery;
- exact object metadata through `head_object`;
- conditional claim markers using `If-None-Match: *`, with owner and ETag-safe
  `If-Match` release;
- copy, verified metadata lookup, and explicit deletion for processing moves;
- creation of the application-owned processing bucket when absent;
- atomic exact-key downloads through a temporary local file;
- bounded prefix downloads that preserve paths below the selected prefix; and
- idempotent client cleanup.

List responses contain bucket, key, size, ETag, and last-modified time but not
content type. Call `get_object_metadata()` before future content-type routing.
The Pydantic `S3ObjectMetadata` record always includes a `content_type` field,
which is `None` when S3 did not supply it.

## Asynchronous boundary

boto3 is blocking. Every SDK call runs with `asyncio.to_thread()` behind a
repository semaphore controlled by `S3_MAX_CONCURRENCY`. Prefix downloads are
also created in bounded batches, rather than creating one task for every object
in a large bucket. boto3 transfer-manager worker threads are disabled for these
downloads so the repository semaphore remains the single concurrency boundary.

Downloads reject absolute and parent-traversal object paths. Completed files
atomically replace the destination; a failed call removes its partial file.
Prefix synchronization replaces matching local files but does not remove
unrelated or stale local files.

## Settings

`S3Settings` reads `S3_*` variables and holds the endpoint, credentials,
region, addressing style, TLS verification, provider, concurrency limit,
processing bucket, and claim TTL.

| Variable | Local value | Meaning |
| --- | --- | --- |
| `S3_PROCESSING_BUCKET` | `documents-processing` | Durable processing objects and claim markers |
| `S3_CLAIM_TTL_SECONDS` | `3600` | Abandoned-claim recovery timeout |
`EmbeddingModelSettings` separately reads:

| Variable | Local value | Meaning |
| --- | --- | --- |
| `EMBEDDINGS_BUCKET` | `models` | RustFS bucket containing model files |
| `EMBEDDINGS_KEY_PREFIX` | `embeddings` | Key prefix synchronized at startup |
| `EMBEDDINGS_LOCAL_DIRECTORY` | `/models/embeddings` | Local volume destination |
| `EMBEDDINGS_RUNTIME` | `onnx` | Shared model runtime |
| `EMBEDDINGS_MODEL_FILE` | `onnx/model.onnx` | Relative model artifact loaded after sync |

For example, `s3://models/embeddings/onnx/model.onnx` becomes
`/models/embeddings/onnx/model.onnx`.

## Lifecycle and current limitation

`BasePipeline.initialize()` first calls the concrete pipeline's preparation
hook. `V1IndexingPipeline` uses it for discovery, conditional claims, and
verified movement to the processing bucket. A missing exact source and
processing object therefore fails before model synchronization, while an empty
or fully claimed selection skips model initialization as a successful no-op.
For a non-empty selection, the base synchronizes the configured model prefix
and v1 loads one `onnxruntime.InferenceSession` from `EMBEDDINGS_MODEL_FILE`.
Cleanup releases the model reference and closes S3 even after initialization
or run failures. An empty model prefix or missing model file fails startup.

The boto3 adapter maps `404`, `NoSuchKey`, and `NotFound` responses for exact
object metadata/download operations to the provider-neutral
`S3ObjectNotFoundError`, retaining the SDK exception as its chained cause.

Embedding inference is not implemented yet; loading the model currently
validates the shared runtime lifecycle for the upcoming embedding step.
