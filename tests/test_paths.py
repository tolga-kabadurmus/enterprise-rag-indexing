import tempfile
import unittest
from pathlib import Path

from app.common.utility.paths import safe_object_destination


class SafeObjectDestinationTests(unittest.TestCase):
    def test_preserves_safe_nested_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            destination = safe_object_destination(root, "onnx/model.onnx")

            self.assertEqual(destination, root / "onnx/model.onnx")

    def test_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "unsafe object key"):
                safe_object_destination(Path(directory), "../secret")

    def test_rejects_absolute_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "unsafe object key"):
                safe_object_destination(Path(directory), "/etc/passwd")


if __name__ == "__main__":
    unittest.main()
