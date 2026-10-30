# V1 indexing pipeline

## Implemented lifecycle

`V1IndexingPipeline` is registered as `--pipeline v1` and performs:

1. resolve an exact `--object-key`, or paginate the complete bucket/prefix;
2. stop successfully without loading a model when the selection is empty;
3. synchronize the configurable S3 embedding-model prefix;
4. load `EMBEDDINGS_MODEL_FILE` once with ONNX Runtime;
5. obtain full `head_object` metadata for every listed object;
6. normalize its MIME type and route it through `DocumentIndexerFactory`;
7. log a truthful per-object status and aggregate batch summary; and
8. release the model and S3 client.

If neither `--object-key` nor `--key-prefix` is supplied, every object in the
source bucket is inspected. Listed objects are processed in bounded batches
with an `asyncio.Semaphore`; the pipeline never creates an unbounded task for
the complete bucket.

If an exact key does not exist, the S3 adapter translates the provider's 404
into `S3ObjectNotFoundError`. The command logs one concise error to stderr and
exits `1` before model synchronization. This is a job-level failure suitable
for Kubernetes CronJob and Argo Workflow/Webhook status handling. If an object
disappears after a bucket listing, that object receives `failed` while the
remaining batch continues.

## Content routing

MIME parameters and casing are normalized. `application/x-pdf` maps to
`application/pdf`. Missing and generic binary MIME values fall back to
`application/pdf` only when the object key ends in `.pdf` case-insensitively.

`DocumentIndexerFactory` currently maps only `application/pdf`. It creates a
`PDFDocumentIndexer` with `PDFChunkerV1`. All other MIME types produce an
explicit `unsupported` result and do not fail other objects.

## Current PDF behavior

`PDFChunkerV1` is a real versioned component boundary, not a simulated success.
It currently returns:

```text
status=not_implemented
chunk_count=0
```

It does not download source PDF bytes, extract text, run OCR, create chunks,
execute embedding inference, or write Qdrant points. Those are later steps.

## Results and logging

The batch summary records discovered, processed, not-implemented, unsupported,
and failed counts. `processed` means metadata inspection completed without an
exception; it does not mean the document was indexed.

DEBUG, INFO, and WARNING records go to stdout. ERROR and CRITICAL records go to
stderr. Expected missing-object errors do not include provider tracebacks;
unexpected per-object exceptions do. Credentials and document content are
never logged.
