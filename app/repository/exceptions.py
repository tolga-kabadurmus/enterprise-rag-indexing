"""Common exceptions raised across infrastructure repositories."""


class S3ObjectNotFoundError(Exception):
    """Report that an exact S3 object does not exist or is not visible.

    Args:
        bucket: Requested S3 bucket.
        object_key: Requested exact object key.

    Notes:
        Adapters should raise this exception from the provider-specific cause
        so diagnostics retain exception chaining without exposing SDK details
        in normal command-line output.
    """

    def __init__(self, bucket: str, object_key: str) -> None:
        self.bucket = bucket
        self.object_key = object_key
        super().__init__(f"Source object not found: s3://{bucket}/{object_key}")
