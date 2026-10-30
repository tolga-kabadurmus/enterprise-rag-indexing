"""Deterministic S3 keys for processing objects and conditional claims."""

from hashlib import sha256
from urllib.parse import quote, unquote


PROCESSING_OBJECT_ROOT = "objects"
CLAIM_ROOT = "claims"
ERROR_OBJECT_ROOT = "error"


def error_object_key(object_key: str) -> str:
    """Return the quarantined key for a failed source document."""

    normalized_key = object_key.strip().lstrip("/")
    if not normalized_key:
        raise ValueError("object_key must not be blank")
    if is_error_object_key(normalized_key):
        return normalized_key
    return f"{ERROR_OBJECT_ROOT}/{normalized_key}"


def is_error_object_key(object_key: str) -> bool:
    """Return whether an object belongs to the error quarantine prefix."""

    return object_key == ERROR_OBJECT_ROOT or object_key.startswith(
        f"{ERROR_OBJECT_ROOT}/"
    )


def processing_object_key(source_bucket: str, object_key: str) -> str:
    """Return the deterministic processing key for an original S3 object."""

    encoded_bucket = quote(source_bucket, safe="")
    encoded_key = quote(object_key, safe="/")
    return f"{PROCESSING_OBJECT_ROOT}/{encoded_bucket}/{encoded_key}"


def processing_object_prefix(
    source_bucket: str,
    key_prefix: str | None = None,
) -> str:
    """Return the processing prefix matching one source bucket selection."""

    base = f"{PROCESSING_OBJECT_ROOT}/{quote(source_bucket, safe='')}/"
    if key_prefix is None:
        return base
    return f"{base}{quote(key_prefix, safe='/')}"


def original_key_from_processing_key(
    source_bucket: str,
    processing_key: str,
) -> str:
    """Recover the original key from a validated processing-object key."""

    prefix = processing_object_prefix(source_bucket)
    if not processing_key.startswith(prefix):
        raise ValueError(
            "processing key does not belong to source bucket: "
            f"{processing_key}"
        )
    original_key = unquote(processing_key.removeprefix(prefix))
    if not original_key:
        raise ValueError("processing object key does not contain a source key")
    return original_key


def claim_object_key(source_bucket: str, object_key: str) -> str:
    """Return a stable lock key without exposing the source key in logs."""

    identity = f"{source_bucket}\0{object_key}".encode("utf-8")
    return f"{CLAIM_ROOT}/{sha256(identity).hexdigest()}.lock"
