# API reference

The reference below is generated from the checked-in Python docstrings.

## Command-line helpers

::: app.cli
    options:
      members: true

## Application entry point

::: app.main
    options:
      members: true

## Job lifecycle

::: app.jobs.base
    options:
      members: true

## Job runner

::: app.jobs.runner
    options:
      members: true

## Pipeline registry

::: app.jobs.registry
    options:
      members: true

## Pipeline base

::: app.pipelines.base
    options:
      members: true

## V1 indexing pipeline

::: app.jobs.v1
    options:
      members: true

## Settings

::: app.common.settings.s3
    options:
      members: true

::: app.common.settings.embedding_service
    options:
      members: true

::: app.common.settings.indexing
    options:
      members: true

::: app.common.settings.pdf_chunking
    options:
      members: true

## Repository factory and models

::: app.repository.factory
    options:
      members: true

::: app.repository.models
    options:
      members: true

::: app.repository.exceptions
    options:
      members: true

## Embedding service repository

::: app.repository.embedding_service.base
    options:
      members: true

::: app.repository.embedding_service.httpx_repository
    options:
      members: true

## S3 repository

::: app.repository.s3.base
    options:
      members: true

::: app.repository.s3.boto3_repository
    options:
      members: true

## Document indexers and PDF chunker

::: app.document_indexers.base
    options:
      members: true

::: app.document_indexers.factory
    options:
      members: true

::: app.document_indexers.pdf
    options:
      members: true

::: app.chunkers.base
    options:
      members: true

::: app.chunkers.pdf.v1
    options:
      members: true

::: app.document_extractors.models
    options:
      members: true

::: app.document_extractors.pdf.v1
    options:
      members: true

## Logging and MIME utilities

::: app.common.utility.logging
    options:
      members: true

::: app.common.utility.mime
    options:
      members: true

::: app.common.utility.processing_keys
    options:
      members: true

## Mock indexing job

::: app.jobs.mock
    options:
      members: true
