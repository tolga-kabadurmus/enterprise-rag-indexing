from io import StringIO
import logging
import unittest

from app.common.utility.logging import configure_standard_logging


class StandardLoggingTests(unittest.TestCase):
    def test_routes_non_errors_to_stdout_and_errors_to_stderr(self) -> None:
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        original_level = root_logger.level
        stdout = StringIO()
        stderr = StringIO()
        try:
            configure_standard_logging(
                level=logging.INFO,
                stdout=stdout,
                stderr=stderr,
            )
            logger = logging.getLogger("tests.standard_logging")

            logger.info("inspection started")
            try:
                raise RuntimeError("broken object")
            except RuntimeError:
                logger.exception("inspection failed")

            self.assertIn("inspection started", stdout.getvalue())
            self.assertNotIn("inspection failed", stdout.getvalue())
            self.assertIn("inspection failed", stderr.getvalue())
            self.assertIn("RuntimeError: broken object", stderr.getvalue())
        finally:
            root_logger.handlers.clear()
            root_logger.handlers.extend(original_handlers)
            root_logger.setLevel(original_level)


if __name__ == "__main__":
    unittest.main()
