from __future__ import annotations

import mimetypes
from pathlib import Path

import boto3

from karaoke_agent.config import Settings


class S3:
  def __init__(self, settings: Settings) -> None:
    self._bucket = settings.s3_bucket
    self._client = boto3.client(
      "s3",
      endpoint_url=settings.s3_endpoint,
      aws_access_key_id=settings.s3_access_key,
      aws_secret_access_key=settings.s3_secret_key,
      region_name=settings.s3_region,
    )

  @property
  def bucket(self) -> str:
    return self._bucket

  def upload_file(self, local_path: Path, key: str, content_type: str | None = None) -> None:
    extra_args = {}
    ct = content_type or mimetypes.guess_type(str(local_path))[0]
    if ct:
      extra_args["ContentType"] = ct
    self._client.upload_file(str(local_path), self._bucket, key, ExtraArgs=extra_args or None)

  def download_file(self, key: str, local_path: Path) -> None:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    self._client.download_file(self._bucket, key, str(local_path))

  def upload_tree(self, local_dir: Path, key_prefix: str) -> None:
    for p in local_dir.rglob("*"):
      if not p.is_file():
        continue
      rel = p.relative_to(local_dir).as_posix()
      key = f"{key_prefix.rstrip('/')}/{rel}"
      self.upload_file(p, key)
