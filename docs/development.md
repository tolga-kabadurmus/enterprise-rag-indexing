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
Pydantic models; future environment configuration must use `BaseSettings`.

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
