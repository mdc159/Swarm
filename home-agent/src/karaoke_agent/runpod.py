from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests


RUNPOD_BASE_URL = "https://api.runpod.ai/v2"


@dataclass(frozen=True)
class RunpodRunResponse:
  id: str
  status: str


class RunpodClient:
  def __init__(self, *, api_key: str, endpoint_id: str) -> None:
    self._api_key = api_key
    self._endpoint_id = endpoint_id
    self._session = requests.Session()
    self._session.headers.update(
      {
        # Runpod docs show "authorization: $RUNPOD_API_KEY"; Bearer also works.
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
      }
    )

  def close(self) -> None:
    self._session.close()

  def run_async(self, payload: dict[str, Any]) -> RunpodRunResponse:
    resp = self._session.post(
      f"{RUNPOD_BASE_URL}/{self._endpoint_id}/run",
      json={"input": payload},
      timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return RunpodRunResponse(id=data["id"], status=data.get("status", ""))

  def status(self, job_id: str) -> dict[str, Any]:
    resp = self._session.get(f"{RUNPOD_BASE_URL}/{self._endpoint_id}/status/{job_id}", timeout=30)
    resp.raise_for_status()
    return resp.json()

  def wait_for_completion(
    self,
    job_id: str,
    *,
    poll_interval_seconds: int = 15,
    timeout_seconds: int = 3600,
  ) -> dict[str, Any]:
    start = time.time()
    backoff = poll_interval_seconds

    while True:
      st = self.status(job_id)
      status = st.get("status")
      if status in ("COMPLETED", "FAILED", "CANCELLED", "TIMED_OUT"):
        return st

      elapsed = time.time() - start
      if elapsed > timeout_seconds:
        raise TimeoutError(f"Runpod job {job_id} did not complete within {timeout_seconds}s")

      time.sleep(backoff)
      backoff = min(backoff * 1.2, 60)
