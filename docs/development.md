# Development

## Python environment

Create the project environment with `virtualenv`:

```bash
python3 -m virtualenv venv
venv/bin/python -m pip install -r requirements.txt
```

Install documentation tooling separately:

```bash
venv/bin/python -m pip install -r requirements-docs.txt
```

## Tests

The current suite uses the standard library:

```bash
venv/bin/python -m unittest discover -s tests -v
```

Repository integration tests must be separate from unit tests and require
explicit RustFS and Qdrant configuration.

The runtime requirements explicitly pin both `pydantic` and
`pydantic-settings`. Data records that cross application boundaries use frozen
Pydantic models. S3, embedding-service, and inactive local-model configuration use separate
`BaseSettings` classes under `app/common/settings`.

The existing virtualenv must have runtime and documentation dependencies
installed before running the complete suite:

```bash
venv/bin/python -m pip install -r requirements.txt -r requirements-docs.txt
```

## Documentation

Preview the site while editing:

```bash
venv/bin/mkdocs serve
```

Build with warnings treated as errors before delivery:

```bash
venv/bin/mkdocs build --strict
```

The generated `site/` directory is ignored. Commit `mkdocs.yml`, Markdown
sources and public Python docstrings, not generated HTML.

## Container development

The root Compose service bind-mounts the local `enterprise-rag-indexing/app`
directory into the container. Python source edits are therefore visible without
rebuilding. Rebuild the image after changing `requirements.txt` or the
Dockerfile.

The service reads `dev-envs/enterprise-rag-indexing.env` from the root
orchestration repository and mounts `indexing-work` at `/work/indexing`. The
embedding service is reached over the Compose network. Indexing closes its
pooled HTTP client after both successful and failed jobs. The workspace is an
ephemeral directory: the application creates one directory per document and
removes it after the attempt. It is not durable processing storage.

Kubernetes should mount an `emptyDir` volume at the same `/work/indexing` path
for a Job or CronJob. Processing documents remain durable in RustFS; pod-local
files may disappear whenever the pod exits. Copy the safe `.env.example` first
and make its credentials match `dev-envs/rustfs.env`.
