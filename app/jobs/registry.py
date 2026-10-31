"""Explicit registry for executable asynchronous indexing pipelines."""

from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.jobs.runner import JobFactory


class IndexingPipelineRegistration(BaseModel):
    """Describe one pipeline exposed by the command-line application.

    Attributes:
        name: Stable command-line name such as ``mock-pdf`` or ``pdf``.
        description: Short human-readable explanation for pipeline discovery.
        job_factory: Composition callable that builds the asynchronous job.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str
    job_factory: JobFactory

    @model_validator(mode="after")
    def validate_text(self) -> Self:
        """Reject blank pipeline names and descriptions."""

        if not self.name.strip():
            raise ValueError("pipeline name must not be empty")
        if not self.description.strip():
            raise ValueError("pipeline description must not be empty")
        return self


class IndexingPipelineRegistry:
    """Resolve explicit pipeline names to asynchronous job factories.

    Dynamic imports are intentionally avoided. The application composition
    layer registers only pipelines that are implemented and safe to execute.

    Args:
        registrations: Pipeline definitions exposed by this application.

    Raises:
        ValueError: If no pipelines are provided or a name is registered more
            than once.
    """

    def __init__(
        self,
        registrations: tuple[IndexingPipelineRegistration, ...],
    ) -> None:
        if not registrations:
            raise ValueError("at least one indexing pipeline must be registered")

        self._registrations: dict[str, IndexingPipelineRegistration] = {}
        for registration in registrations:
            if registration.name in self._registrations:
                raise ValueError(
                    f"pipeline is already registered: {registration.name}"
                )
            self._registrations[registration.name] = registration

    @property
    def names(self) -> tuple[str, ...]:
        """Return registered pipeline names in deterministic order."""

        return tuple(sorted(self._registrations))

    @property
    def registrations(self) -> tuple[IndexingPipelineRegistration, ...]:
        """Return registrations ordered by their command-line names."""

        return tuple(self._registrations[name] for name in self.names)

    def resolve(self, name: str) -> JobFactory:
        """Return the job factory registered for ``name``.

        Args:
            name: Exact pipeline name accepted by the CLI.

        Returns:
            Factory that constructs the selected asynchronous job.

        Raises:
            KeyError: If the name is not registered.
        """

        try:
            return self._registrations[name].job_factory
        except KeyError as error:
            raise KeyError(f"unknown indexing pipeline: {name}") from error
