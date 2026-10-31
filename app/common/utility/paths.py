"""Filesystem path helpers for downloaded object keys."""

from pathlib import Path, PurePosixPath


def safe_object_destination(root: Path, relative_key: str) -> Path:
    """Resolve an object key below ``root`` without allowing path traversal.

    Args:
        root: Local directory that must contain the downloaded object.
        relative_key: Object key relative to the selected S3 prefix.

    Returns:
        A normalized local destination below ``root``.

    Raises:
        ValueError: If the key is empty, absolute, or contains traversal.
    """

    key_path = PurePosixPath(relative_key)
    if not relative_key or key_path.is_absolute() or ".." in key_path.parts:
        raise ValueError(f"unsafe object key: {relative_key!r}")
    if any(part in {"", "."} for part in key_path.parts):
        raise ValueError(f"unsafe object key: {relative_key!r}")

    destination = root.joinpath(*key_path.parts)
    resolved_root = root.resolve()
    resolved_destination = destination.resolve()
    if not resolved_destination.is_relative_to(resolved_root):
        raise ValueError(f"object key escapes destination: {relative_key!r}")
    return destination
