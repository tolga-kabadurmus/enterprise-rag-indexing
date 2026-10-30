"""MIME normalization helpers for document routing."""

from pathlib import PurePosixPath

PDF_CONTENT_TYPE = "application/pdf"
GENERIC_CONTENT_TYPES = {
    "application/octet-stream",
    "binary/octet-stream",
}


def normalize_content_type(
    content_type: str | None,
    object_key: str,
) -> str | None:
    """Normalize an S3 content type with a conservative extension fallback.

    Args:
        content_type: MIME value returned by S3 object metadata.
        object_key: Source key used only when the MIME value is absent or
            generic.

    Returns:
        A lowercase MIME type without parameters, ``application/pdf`` for a
        PDF extension fallback, or ``None`` when no useful type is available.
    """

    normalized = None
    if content_type is not None:
        normalized = content_type.partition(";")[0].strip().lower() or None

    if normalized == "application/x-pdf":
        return PDF_CONTENT_TYPE
    if normalized is None or normalized in GENERIC_CONTENT_TYPES:
        if PurePosixPath(object_key).suffix.lower() == ".pdf":
            return PDF_CONTENT_TYPE
    return normalized
