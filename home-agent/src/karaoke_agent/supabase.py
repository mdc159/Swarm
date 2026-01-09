from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from karaoke_agent.config import Settings


@dataclass(frozen=True)
class Job:
  job_id: str
  source_url: str
  prefer_local_split: bool
  s3_input_key: str
  s3_output_prefix: str
  title: str | None
  artist: str | None
  processing_status: str
  runpod_job_id: str | None

  @staticmethod
  def from_row(row: dict[str, Any]) -> "Job":
    job_id = row["job_id"]
    return Job(
      job_id=job_id,
      source_url=row.get("source_url") or "",
      prefer_local_split=bool(row.get("prefer_local_split") or False),
      s3_input_key=f"karaoke/in/{job_id}/source.mp4",
      s3_output_prefix=f"karaoke/out/{job_id}/",
      title=row.get("title"),
      artist=row.get("artist"),
      processing_status=row.get("processing_status") or "queued",
      runpod_job_id=row.get("runpod_job_id"),
    )


class Supabase:
  def __init__(self, settings: Settings) -> None:
    self._url = settings.supabase_url.rstrip("/")
    self._key = settings.supabase_service_role_key
    self._session = requests.Session()
    self._session.headers.update(
      {
        "apikey": self._key,
        "Authorization": f"Bearer {self._key}",
        "Content-Type": "application/json",
      }
    )

  def close(self) -> None:
    self._session.close()

  def rpc(self, fn: str, payload: dict[str, Any]) -> Any:
    resp = self._session.post(f"{self._url}/rest/v1/rpc/{fn}", json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()

  def claim_job(
    self,
    worker_id: str,
    has_nvidia_gpu: bool,
    demucs_available: bool,
    lease_seconds: int,
    max_attempts: int,
  ) -> Job | None:
    rows = self.rpc(
      "claim_karaoke_job",
      {
        "worker_id": worker_id,
        "has_nvidia_gpu": has_nvidia_gpu,
        "demucs_available": demucs_available,
        "lease_seconds": lease_seconds,
        "max_attempts": max_attempts,
      },
    )

    if not rows:
      return None

    # PostgREST returns an array for SETOF return type.
    row = rows[0] if isinstance(rows, list) else rows
    return Job.from_row(row)

  def renew_lease(self, job_id: str, worker_id: str, lease_seconds: int) -> bool:
    result = self.rpc(
      "renew_karaoke_job_lease",
      {"job_id": job_id, "worker_id": worker_id, "lease_seconds": lease_seconds},
    )

    # PostgREST returns scalar results as JSON. Depending on configuration, it may
    # be a bool or an object.
    if isinstance(result, bool):
      return result
    if isinstance(result, dict) and "renew_karaoke_job_lease" in result:
      return bool(result["renew_karaoke_job_lease"])
    return bool(result)

  def update_job(
    self,
    job_id: str,
    status: str,
    *,
    last_error: str | None = None,
    runpod_job_id: str | None = None,
    public_url: str | None = None,
    duration_seconds: float | None = None,
    extra: dict[str, Any] | None = None,
  ) -> dict[str, Any]:
    payload: dict[str, Any] = {"processing_status": status, "updated_at": datetime.utcnow().isoformat()}
    if last_error is not None:
      payload["last_error"] = last_error
    if runpod_job_id is not None:
      payload["runpod_job_id"] = runpod_job_id
    if public_url is not None:
      payload["public_url"] = public_url
    if duration_seconds is not None:
      payload["duration"] = int(duration_seconds)
    if extra:
      payload.update(extra)

    resp = self._session.patch(
      f"{self._url}/rest/v1/karaoke_jobs?job_id=eq.{job_id}",
      headers={"Prefer": "return=representation"},
      json=payload,
      timeout=30,
    )
    resp.raise_for_status()
    data: Any = resp.json()
    if isinstance(data, list):
      first = data[0] if data else None
      return first if isinstance(first, dict) else {}
    if isinstance(data, dict):
      return data
    return {}

  def insert_job(
    self,
    *,
    job_id: str,
    source_url: str,
    title: str | None,
    artist: str | None,
    prefer_local_split: bool,
  ) -> dict[str, Any]:
    payload: dict[str, Any] = {
      "job_id": job_id,
      "source_url": source_url,
      "title": title,
      "artist": artist,
      "prefer_local_split": prefer_local_split,
      "processing_status": "queued",
    }
    resp = self._session.post(
      f"{self._url}/rest/v1/karaoke_jobs",
      headers={"Prefer": "return=representation"},
      json=payload,
      timeout=30,
    )
    resp.raise_for_status()
    data: Any = resp.json()
    if isinstance(data, list):
      first = data[0] if data else None
      return first if isinstance(first, dict) else {}
    if isinstance(data, dict):
      return data
    return {}
