"""S3-compatible repository contracts and implementations."""

from app.repository.s3.base import S3Repository
from app.repository.s3.boto3_repository import Boto3S3Repository

__all__ = ["Boto3S3Repository", "S3Repository"]
