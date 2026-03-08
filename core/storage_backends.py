# core/storage_backends.py
from __future__ import annotations

from django.conf import settings
from botocore.exceptions import ClientError
from storages.backends.s3boto3 import S3Boto3Storage


class MediaStorage(S3Boto3Storage):
    '''
    S3 backend for user-uploaded media (images, etc.).

    LocalMarketNE v1 does not serve paid orders, so we only maintain media storage.
    '''
    location = "media"
    default_acl = None
    file_overwrite = False
    # django-storages expects AWS_STORAGE_BUCKET_NAME by default.
    # We store media bucket in AWS_S3_MEDIA_BUCKET, so wire it explicitly.
    bucket_name = (
        getattr(settings, "AWS_S3_MEDIA_BUCKET", "")
        or getattr(settings, "AWS_STORAGE_BUCKET_NAME", "")
        or None
    )

    def exists(self, name: str) -> bool:
        """
        Some IAM policies allow PutObject but deny HeadObject/ListBucket.
        django-storages may call exists() during save, which can raise 403.
        Treat that as "object does not exist" so uploads can proceed.
        """
        try:
            return super().exists(name)
        except ClientError as exc:
            code = str((exc.response or {}).get("Error", {}).get("Code", ""))
            if code in {"403", "AccessDenied"}:
                return False
            raise


def get_media_storage_class():
    return MediaStorage


def using_s3() -> bool:
    return bool(getattr(settings, "USE_S3", False))
