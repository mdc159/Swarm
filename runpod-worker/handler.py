import json
import os
import shutil
import subprocess
from pathlib import Path

import boto3
import runpod

STEM_IDS = ["vocals", "drums", "bass", "guitar", "piano", "other"]


def _env(name: str, default: str | None = None) -> str | None:
  v = os.getenv(name)
  return v if v is not None and v != "" else default


def _run(cmd: list[str]) -> None:
  proc = subprocess.run(cmd, capture_output=True, text=True)
  if proc.returncode != 0:
    raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr}")


def _s3_client():
  return boto3.client(
    "s3",
    endpoint_url=_env("S3_ENDPOINT"),
    aws_access_key_id=_env("S3_ACCESS_KEY"),
    aws_secret_access_key=_env("S3_SECRET_KEY"),
    region_name=_env("S3_REGION", "us-east-1"),
  )


def _extract_video_only(source_mp4: Path, out_mp4: Path) -> None:
  _run(["ffmpeg", "-y", "-i", str(source_mp4), "-an", "-c:v", "copy", str(out_mp4)])


def _extract_audio_wav(source_mp4: Path, out_wav: Path) -> None:
  _run(
    [
      "ffmpeg",
      "-y",
      "-i",
      str(source_mp4),
      "-vn",
      "-ac",
      "2",
      "-ar",
      "44100",
      "-c:a",
      "pcm_s16le",
      str(out_wav),
    ]
  )


def _wav_to_m4a(wav_path: Path, m4a_path: Path) -> None:
  _run(["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "aac", "-b:a", "192k", str(m4a_path)])


def _build_multi_audio_mp4(video_only_mp4: Path, stem_m4as: dict[str, Path], out_mp4: Path) -> None:
  cmd = ["ffmpeg", "-y", "-i", str(video_only_mp4)]
  for stem in STEM_IDS:
    cmd += ["-i", str(stem_m4as[stem])]

  cmd += ["-map", "0:v"]
  for i in range(1, 7):
    cmd += ["-map", f"{i}:a"]

  cmd += ["-c:v", "copy", "-c:a", "copy", "-shortest", str(out_mp4)]
  _run(cmd)


def _run_demucs(audio_wav: Path, out_dir: Path, model: str) -> dict[str, Path]:
  out_dir.mkdir(parents=True, exist_ok=True)
  _run(["python3", "-m", "demucs", "-n", model, "--out", str(out_dir), str(audio_wav)])

  separated = out_dir / "separated" / model / audio_wav.stem
  stems: dict[str, Path] = {}
  for stem in STEM_IDS:
    p = separated / f"{stem}.wav"
    if not p.exists():
      raise RuntimeError(f"Missing demucs output: {p}")
    stems[stem] = p
  return stems


def handler(job: dict) -> dict:
  inp = job.get("input") or {}

  job_id = inp["job_id"]
  bucket = inp["bucket"]
  input_key = inp["input_key"]
  output_prefix = inp["output_prefix"]
  model = inp.get("model", "htdemucs_6s")
  create_canonical_mp4 = bool(inp.get("create_canonical_mp4", True))
  metadata = inp.get("metadata") or {}

  s3 = _s3_client()

  base = Path("/tmp/work")
  shutil.rmtree(base, ignore_errors=True)
  in_dir = base / "in"
  out_dir = base / "out"
  tmp_dir = base / "tmp"
  for d in (in_dir, out_dir, tmp_dir):
    d.mkdir(parents=True, exist_ok=True)

  source_mp4 = in_dir / "source.mp4"
  s3.download_file(bucket, input_key, str(source_mp4))

  # Outputs
  video_only = out_dir / "video.mp4"
  audio_wav = tmp_dir / "audio.wav"
  demucs_out = tmp_dir / "demucs"

  _extract_video_only(source_mp4, video_only)
  _extract_audio_wav(source_mp4, audio_wav)

  stem_wavs = _run_demucs(audio_wav, demucs_out, model)

  stem_m4as: dict[str, Path] = {}
  for stem, wav in stem_wavs.items():
    m4a = out_dir / f"{stem}.m4a"
    _wav_to_m4a(wav, m4a)
    stem_m4as[stem] = m4a

  stems_json = {
    "title": metadata.get("title", ""),
    "artist": metadata.get("artist", ""),
    "video": "video.mp4",
    "stems": [
      {"id": "vocals", "name": "Vocals", "file": "vocals.m4a"},
      {"id": "drums", "name": "Drums", "file": "drums.m4a"},
      {"id": "bass", "name": "Bass", "file": "bass.m4a"},
      {"id": "guitar", "name": "Guitar", "file": "guitar.m4a"},
      {"id": "piano", "name": "Piano", "file": "piano.m4a"},
      {"id": "other", "name": "Other", "file": "other.m4a"},
    ],
  }
  (out_dir / "stems.json").write_text(json.dumps(stems_json, indent=2))

  uploads: list[dict[str, str]] = []

  def upload(local: Path, rel_key: str, content_type: str | None = None) -> None:
    key = f"{output_prefix.rstrip('/')}/{rel_key}"
    extra = {}
    if content_type:
      extra["ContentType"] = content_type
    s3.upload_file(str(local), bucket, key, ExtraArgs=extra or None)
    uploads.append({"file": rel_key, "key": key})

  upload(video_only, "video.mp4", "video/mp4")
  for stem in STEM_IDS:
    upload(stem_m4as[stem], f"{stem}.m4a", "audio/mp4")
  upload(out_dir / "stems.json", "stems.json", "application/json")

  if create_canonical_mp4:
    karaoke_mp4 = out_dir / "karaoke_six_stem.mp4"
    _build_multi_audio_mp4(video_only, stem_m4as, karaoke_mp4)
    upload(karaoke_mp4, "karaoke_six_stem.mp4", "video/mp4")

  return {
    "status": "ok",
    "job_id": job_id,
    "bucket": bucket,
    "output_prefix": output_prefix,
    "uploads": uploads,
    "uploaded_count": len(uploads),
  }


runpod.serverless.start({"handler": handler})
