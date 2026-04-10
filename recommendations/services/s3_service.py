import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from botocore.exceptions import ClientError
from fastapi import UploadFile

from recommendations.adapters.s3.client import get_s3_client
from recommendations.core.config import settings
from recommendations.exceptions.exceptions import BadRequestException, NotFoundException


_VALID_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,49}$")


class S3Service:
    def __init__(self):
        self.s3 = get_s3_client()
        self.bucket = settings.s3_bucket_name

    def _validate_client(self, client: str) -> str:
        client_value = (client or "").strip().lower()
        if not client_value or not _VALID_SEGMENT_RE.match(client_value):
            raise BadRequestException("Invalid client. Use lowercase letters, digits, '_' or '-'.")

        allowed = settings.parsed_s3_allowed_clients
        if allowed and client_value not in allowed:
            raise BadRequestException(f"Client '{client_value}' is not allowed.")

        return client_value

    def _validate_dataset(self, dataset: str) -> str:
        dataset_value = (dataset or "").strip().lower()
        if not dataset_value or not _VALID_SEGMENT_RE.match(dataset_value):
            raise BadRequestException("Invalid dataset. Use lowercase letters, digits, '_' or '-'.")

        allowed = settings.parsed_s3_allowed_datasets
        if allowed and dataset_value not in allowed:
            raise BadRequestException(f"Dataset '{dataset_value}' is not allowed.")

        return dataset_value

    def _sanitize_filename(self, filename: str) -> str:
        cleaned = os.path.basename((filename or "").strip())
        if not cleaned or "/" in cleaned or "\\" in cleaned:
            raise BadRequestException("Invalid filename.")
        return cleaned

    def _build_key(self, client: str, dataset: str, filename: str) -> str:
        return f"{client}/{dataset}/{filename}"

    def sync_latest_to_processed(
        self,
        client: str,
        datasets: list[str] | None = None,
        overwrite: bool = True,
    ) -> dict[str, Any]:
        client_value = self._validate_client(client)

        if datasets:
            dataset_values = [self._validate_dataset(ds) for ds in datasets]
        else:
            dataset_values = self._discover_datasets(client_value)

        if not dataset_values:
            raise NotFoundException(f"No datasets found under client '{client_value}'.")

        base_dir = Path(__file__).resolve().parents[1] / "pipelines" / "data" / "processed" / client_value
        base_dir.mkdir(parents=True, exist_ok=True)

        synced: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for dataset_value in dataset_values:
            key = self._resolve_key(client_value, dataset_value, None)
            filename = key.split("/")[-1]
            target_dir = base_dir / dataset_value
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / filename

            if target_file.exists() and not overwrite:
                skipped.append(
                    {
                        "dataset": dataset_value,
                        "key": key,
                        "path": str(target_file),
                        "reason": "exists",
                    }
                )
                continue

            self.s3.download_file(self.bucket, key, str(target_file))

            synced.append(
                {
                    "dataset": dataset_value,
                    "key": key,
                    "path": str(target_file),
                    "filename": filename,
                }
            )

        return {
            "bucket": self.bucket,
            "client": client_value,
            "processed_base_path": str(base_dir),
            "synced_count": len(synced),
            "skipped_count": len(skipped),
            "synced": synced,
            "skipped": skipped,
        }

    def upload_file(self, client: str, dataset: str, file: UploadFile) -> dict[str, Any]:
        client_value = self._validate_client(client)
        dataset_value = self._validate_dataset(dataset)

        if file is None or not file.filename:
            raise BadRequestException("A file is required.")

        filename = self._sanitize_filename(file.filename)
        key = self._build_key(client_value, dataset_value, filename)

        max_bytes = settings.s3_max_upload_mb * 1024 * 1024
        upload_size = file.size if file.size is not None else 0
        if upload_size and upload_size > max_bytes:
            raise BadRequestException(f"File too large. Max allowed is {settings.s3_max_upload_mb}MB.")

        extra_args = {
            "ContentType": file.content_type or "application/octet-stream",
            "ServerSideEncryption": "AES256",
        }

        try:
            self.s3.upload_fileobj(file.file, self.bucket, key, ExtraArgs=extra_args)
            meta = self.s3.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            raise BadRequestException(f"S3 upload failed: {exc}") from exc
        finally:
            file.file.close()

        return {
            "bucket": self.bucket,
            "client": client_value,
            "dataset": dataset_value,
            "key": key,
            "filename": filename,
            "size": meta.get("ContentLength", 0),
            "content_type": meta.get("ContentType", "application/octet-stream"),
            "etag": str(meta.get("ETag", "")).replace('"', ""),
            "last_modified": self._to_iso(meta.get("LastModified")),
        }

    def fetch_file(self, client: str, dataset: str, filename: str | None = None):
        client_value = self._validate_client(client)
        dataset_value = self._validate_dataset(dataset)

        key = self._resolve_key(client_value, dataset_value, filename)

        try:
            response = self.s3.get_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            raise NotFoundException(f"File not found in S3 for key '{key}'.") from exc

        return {
            "bucket": self.bucket,
            "key": key,
            "filename": key.split("/")[-1],
            "content_type": response.get("ContentType", "application/octet-stream"),
            "stream": response["Body"],
        }

    def list_files(
        self,
        client: str,
        dataset: str | None = None,
        max_keys: int | None = None,
        continuation_token: str | None = None,
        include_download_url: bool = False,
    ) -> dict[str, Any]:
        client_value = self._validate_client(client)

        if dataset:
            dataset_value = self._validate_dataset(dataset)
            prefix = f"{client_value}/{dataset_value}/"
        else:
            prefix = f"{client_value}/"

        safe_max = min(max_keys or settings.s3_list_max_keys, settings.s3_list_max_keys)

        kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Prefix": prefix,
            "MaxKeys": safe_max,
        }
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token

        response = self.s3.list_objects_v2(**kwargs)

        items: list[dict[str, Any]] = []
        for obj in response.get("Contents", []):
            key = obj["Key"]
            record = {
                "key": key,
                "filename": key.split("/")[-1],
                "size": obj.get("Size", 0),
                "last_modified": self._to_iso(obj.get("LastModified")),
            }
            if include_download_url:
                record["download_url"] = self.s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": key},
                    ExpiresIn=settings.s3_presign_expiry_seconds,
                )
            items.append(record)

        return {
            "bucket": self.bucket,
            "client": client_value,
            "prefix": prefix,
            "count": len(items),
            "files": items,
            "next_token": response.get("NextContinuationToken"),
            "is_truncated": response.get("IsTruncated", False),
        }

    def _resolve_key(self, client: str, dataset: str, filename: str | None) -> str:
        if filename:
            return self._build_key(client, dataset, self._sanitize_filename(filename))

        prefix = f"{client}/{dataset}/"
        response = self.s3.list_objects_v2(Bucket=self.bucket, Prefix=prefix, MaxKeys=200)
        items = response.get("Contents", [])
        if not items:
            raise NotFoundException(f"No files found for '{prefix}'.")

        latest = sorted(items, key=lambda x: x.get("LastModified", datetime.min.replace(tzinfo=timezone.utc)), reverse=True)[0]
        return latest["Key"]

    def _discover_datasets(self, client: str) -> list[str]:
        paginator = self.s3.get_paginator("list_objects_v2")
        datasets: set[str] = set()

        for page in paginator.paginate(Bucket=self.bucket, Prefix=f"{client}/", Delimiter="/"):
            for pref in page.get("CommonPrefixes", []):
                prefix = pref.get("Prefix", "")
                parts = prefix.strip("/").split("/")
                if len(parts) >= 2 and parts[0] == client:
                    datasets.add(parts[1])

        return sorted(datasets)

    @staticmethod
    def _to_iso(dt: Any) -> str | None:
        if dt is None:
            return None
        if hasattr(dt, "isoformat"):
            return dt.isoformat()
        return str(dt)
