# Command line

The reusable parser is defined in `app.cli`. A concrete application entry point
passes its job factory to `run_job_cli`.

## Arguments

| Argument | Required | Meaning |
| --- | --- | --- |
| `--source-bucket` | yes | Bucket containing source documents |
| `--object-key` | no | Index exactly one object |
| `--key-prefix` | no | Index eligible objects under a prefix |
| `--concurrency` | no | Maximum concurrent documents; default `4` |

`--object-key` and `--key-prefix` are mutually exclusive. Omitting both means
the concrete job may discover all eligible objects in the bucket.

## Selection examples

Index one object:

```bash
python -m app.main \
  --source-bucket documents \
  --object-key contracts/contract.pdf \
  --concurrency 2
```

Index a prefix:

```bash
python -m app.main \
  --source-bucket documents \
  --key-prefix contracts/2026/ \
  --concurrency 4
```

!!! note

    `app.main` is the planned concrete composition entry point and does not
    exist yet. These examples document the established CLI contract rather
    than claiming that the PDF pipeline is executable today.

## Composition example

The future entry point should remain small:

```python
import logging

from app.cli import run_job_cli
from app.jobs.pdf import PDFDocumentIndexing


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(run_job_cli(PDFDocumentIndexing))
```

The factory receives `IndexingJobArguments`; provider clients belong in the
composition layer and are injected into the concrete job or its controller.
