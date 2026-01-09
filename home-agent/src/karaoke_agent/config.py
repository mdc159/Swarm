from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
  """Load a .env file into os.environ (without overwriting existing vars)."""

  if not path.exists():
    return

  for raw in path.read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith("#"):
      continue
    if "=" not in line:
      continue
    k, v = line.split("=", 1)
    k = k.strip()
    v = v.strip().strip('"').strip("'")
    if k and k not in os.environ:
      os.environ[k] = v


def _req(name: str) -> str:
  v = os.getenv(name)
  if v is None or v == "":
    raise RuntimeError(f"Missing required env var: {name}")
  return v


def _opt(name: str) -> str | None:
  v = os.getenv(name)
  return v if v not in (None, "") else None


def _bool(name: str, default: bool = False) -> bool:
  v = os.getenv(name)
  if v is None or v == "":
    return default
  return v.strip().lower() in ("1", "true", "yes", "y", "on")


def _int(name: str, default: int) -> int:
  v = os.getenv(name)
  if v is None or v == "":
    return default
  return int(v)


@dataclass(frozen=True)
class Settings:
  # Supabase
  supabase_url: str
  supabase_service_role_key: str

  # S3
  s3_endpoint: str
  s3_bucket: str
  s3_access_key: str
  s3_secret_key: str
  s3_region: str

  # Worker
  worker_id: str
  poll_interval_seconds: int
  lease_seconds: int
  max_attempts: int
  download_dir: Path

  # Capabilities
  has_nvidia_gpu: bool
  demucs_available: bool

  # Runpod
  runpod_api_key: str | None
  runpod_endpoint_id: str | None
  runpod_poll_interval_seconds: int

  # Optional publishing
  public_base_url: str | None

  def ensure_dirs(self) -> None:
    self.download_dir.mkdir(parents=True, exist_ok=True)


def load_settings(env_file: str | None = None) -> Settings:
  env_path = Path(env_file) if env_file else Path(".env")
  _load_dotenv(env_path)

  return Settings(
    supabase_url=_req("SUPABASE_URL").rstrip("/"),
    supabase_service_role_key=_req("SUPABASE_SERVICE_ROLE_KEY"),
    s3_endpoint=_req("S3_ENDPOINT"),
    s3_bucket=_req("S3_BUCKET"),
    s3_access_key=_req("S3_ACCESS_KEY"),
    s3_secret_key=_req("S3_SECRET_KEY"),
    s3_region=os.getenv("S3_REGION", "us-east-1"),
    worker_id=_req("WORKER_ID"),
    poll_interval_seconds=_int("POLL_INTERVAL", 30),
    lease_seconds=_int("LEASE_SECONDS", 900),
    max_attempts=_int("MAX_ATTEMPTS", 3),
    download_dir=Path(os.getenv("DOWNLOAD_DIR", "/var/lib/karaoke-agent/spool")),
    has_nvidia_gpu=_bool("HAS_NVIDIA_GPU", False),
    demucs_available=_bool("DEMUCS_AVAILABLE", False),
    runpod_api_key=_opt("RUNPOD_API_KEY"),
    runpod_endpoint_id=_opt("RUNPOD_ENDPOINT_ID"),
    runpod_poll_interval_seconds=_int("RUNPOD_POLL_INTERVAL", 15),
    public_base_url=_opt("PUBLIC_BASE_URL"),
  )
