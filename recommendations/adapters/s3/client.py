import boto3

from recommendations.core.config import settings


def get_s3_client():
    kwargs = {"region_name": settings.s3_region}

    if settings.aws_access_key_id.strip() and settings.aws_secret_access_key.strip():
        kwargs["aws_access_key_id"] = settings.aws_access_key_id.strip()
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key.strip()

    if settings.aws_session_token.strip():
        kwargs["aws_session_token"] = settings.aws_session_token.strip()

    if settings.s3_endpoint_url.strip():
        kwargs["endpoint_url"] = settings.s3_endpoint_url.strip()

    return boto3.client("s3", **kwargs)
