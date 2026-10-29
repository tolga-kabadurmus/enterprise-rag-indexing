import unittest

from app.cli import parse_job_arguments


class ParseJobArgumentsTests(unittest.TestCase):
    def test_parses_exact_object_key(self) -> None:
        arguments = parse_job_arguments(
            [
                "--source-bucket",
                "documents",
                "--object-key",
                "contracts/contract.pdf",
                "--concurrency",
                "2",
            ]
        )

        self.assertEqual(arguments.source_bucket, "documents")
        self.assertEqual(arguments.object_key, "contracts/contract.pdf")
        self.assertIsNone(arguments.key_prefix)
        self.assertEqual(arguments.concurrency, 2)

    def test_parses_key_prefix(self) -> None:
        arguments = parse_job_arguments(
            ["--source-bucket", "documents", "--key-prefix", "contracts/"]
        )

        self.assertEqual(arguments.key_prefix, "contracts/")
        self.assertIsNone(arguments.object_key)

    def test_rejects_object_key_and_prefix_together(self) -> None:
        with self.assertRaises(SystemExit):
            parse_job_arguments(
                [
                    "--source-bucket",
                    "documents",
                    "--object-key",
                    "contract.pdf",
                    "--key-prefix",
                    "contracts/",
                ]
            )

    def test_rejects_zero_concurrency(self) -> None:
        with self.assertRaises(SystemExit):
            parse_job_arguments(
                ["--source-bucket", "documents", "--concurrency", "0"]
            )


if __name__ == "__main__":
    unittest.main()
