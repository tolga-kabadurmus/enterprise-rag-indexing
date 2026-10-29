import unittest

from pydantic import BaseModel, ValidationError

from app.cli import IndexingCommandArguments
from app.jobs.base import IndexingJobArguments
from app.jobs.mock import MockIndexedChunk
from app.jobs.registry import IndexingPipelineRegistration


class PydanticModelTests(unittest.TestCase):
    def test_all_application_data_records_are_pydantic_models(self) -> None:
        model_types = (
            IndexingCommandArguments,
            IndexingJobArguments,
            MockIndexedChunk,
            IndexingPipelineRegistration,
        )

        for model_type in model_types:
            with self.subTest(model=model_type.__name__):
                self.assertTrue(issubclass(model_type, BaseModel))

    def test_job_arguments_are_frozen(self) -> None:
        arguments = IndexingJobArguments(source_bucket="documents")

        with self.assertRaises(ValidationError):
            arguments.concurrency = 8

    def test_job_arguments_reject_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            IndexingJobArguments(
                source_bucket="documents",
                unsupported_option=True,
            )


if __name__ == "__main__":
    unittest.main()
