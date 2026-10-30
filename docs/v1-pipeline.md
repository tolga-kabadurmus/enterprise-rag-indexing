# V1 indexing pipeline

## Implemented lifecycle

`V1IndexingPipeline` is registered as `--pipeline v1` and performs:

1. ensure the configured processing bucket exists;
2. discover the exact key or complete source bucket/prefix plus resumable
   processing objects;
3. acquire a conditional claim for each source identity;
4. copy new sources to the processing bucket, verify their size, then delete
   the source copy;
5. skip embedding-service initialization when the selection is empty or every claim was
   won by another job;
6. use the injected pooled HTTPX embedding repository;
7. download each claimed processing PDF into the ephemeral workspace;
8. extract embedded page text and create page-bounded chunks;
9. request one vector per chunk in batches bounded by text count and aggregate
   characters;
10. upsert deterministic chunk points to the named Qdrant `dense` vector with
    chunk text and citation metadata;
11. on embedding or Qdrant failure, copy the document to
    `error/<original-object-key>` in its source bucket, verify the copy, and
    delete the processing copy; and
12. remove temporary files, release claims, and close Qdrant, HTTPX, and S3
    clients. Successfully indexed processing objects remain durable.

Discovery, claiming, and document processing use bounded batches. The pipeline
does not create a task for every object in a large bucket.

## Claim and recovery behavior

A move between S3 buckets is copy-plus-delete, not an atomic rename. V1 creates
a zero-byte claim marker with `If-None-Match: *`; only one overlapping job can
claim a source bucket/key identity. A processing copy is verified by size
before the source is deleted. If both copies exist after a crash, the processing
copy is preferred and the verified source copy is removed by the next owner.
Claim release verifies the owner metadata and deletes with `If-Match` against
the marker ETag, so an older attempt cannot remove a replacement owner's claim.

Processing keys deterministically include the original source bucket and key.
Later invocations discover these objects and can resume them. Claims are
released after each attempt. A hard process/pod termination can leave a marker;
it becomes reclaimable after `S3_CLAIM_TTL_SECONDS`. This lease timeout means an
operation running longer than the TTL could overlap with a reclaimer, so choose
a value longer than the expected job duration.

An exact key missing from both source and processing raises
`S3ObjectNotFoundError`, logs a concise stderr record, and exits `1` before
any embedding-service request.

Whole-bucket discovery excludes the source bucket's `error/` prefix so failed
documents remain quarantined across scheduled runs. An operator can explicitly
select `--key-prefix error/` to retry them. An embedding or Qdrant failure is isolated to
its document, but the completed command returns exit status `1` when any object
failed.

## Text extraction and chunking

`DocumentIndexerFactory` maps normalized `application/pdf` to
`PDFDocumentIndexer`, which composes two responsibilities:

- `PDFTextExtractorV1` reads a local PDF with `pypdf` outside the event loop;
- `PDFChunkerV1` normalizes and splits each page independently.

Chunk size and overlap are controlled by `PDF_CHUNK_SIZE` and
`PDF_CHUNK_OVERLAP`. A chunk never crosses pages. Empty-text PDFs return
`status=empty`; supported PDFs with text return `status=chunked`.

The implementation uses embedded text only. It does not run OCR, interpret
images, reconstruct layout, or preserve table structure. Text that `pypdf`
extracts from table cells is treated as ordinary text.

## Citation output

Every `DocumentChunk` contains deterministic `document_id` and `chunk_id`, the
original source bucket/key, one-based page number, document/page chunk ordinals,
normalized character offsets, ETag, content type, and processing location.
These fields and chunk text are stored in the Qdrant payload; chunk text is
never written to normal logs. `chunk_id` is the deterministic point ID, making
retries idempotent.

Startup validates named `dense` and `sparse` vectors and requires IDF for
`sparse`. Points currently contain only `dense` because the embedding service
does not yet return sparse vectors. Hybrid retrieval remains inactive until a
real sparse encoder is implemented.
