"""Standard-stream logging configuration for command-line jobs."""

import logging
import sys
from typing import TextIO


class MaximumLevelFilter(logging.Filter):
    """Allow records strictly below a configured logging level."""

    def __init__(self, maximum_level: int) -> None:
        super().__init__()
        self.maximum_level = maximum_level

    def filter(self, record: logging.LogRecord) -> bool:
        """Return whether ``record`` belongs on the lower-severity stream."""

        return record.levelno < self.maximum_level


def configure_standard_logging(
    level: int = logging.INFO,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    """Send non-error logs to stdout and errors with tracebacks to stderr.

    Args:
        level: Root logger threshold.
        stdout: Optional stream override used by tests.
        stderr: Optional stream override used by tests.

    Side Effects:
        Replaces handlers on the root logger to avoid duplicated records.
    """

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    stdout_handler = logging.StreamHandler(stdout or sys.stdout)
    stdout_handler.setLevel(level)
    stdout_handler.addFilter(MaximumLevelFilter(logging.ERROR))
    stdout_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler(stderr or sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)
