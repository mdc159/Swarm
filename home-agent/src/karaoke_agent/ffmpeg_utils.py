from __future__ import annotations

import json
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
  pass


def _run(cmd: list[str]) -> None:
  proc = subprocess.run(cmd, capture_output=True, text=True)
  if proc.returncode != 0:
    raise FFmpegError(f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stderr}")


def get_duration_seconds(media_path: Path) -> float:
  # Uses ffprobe.
  cmd = [
    "ffprobe",
    "-v",
    "error",
    "-show_entries",
    "format=duration",
    "-of",
    "json",
    str(media_path),
  ]
  proc = subprocess.run(cmd, capture_output=True, text=True)
  if proc.returncode != 0:
    raise FFmpegError(proc.stderr)
  data = json.loads(proc.stdout)
  dur = data.get("format", {}).get("duration")
  return float(dur) if dur is not None else 0.0


def extract_video_only(source_mp4: Path, out_mp4: Path) -> None:
  out_mp4.parent.mkdir(parents=True, exist_ok=True)
  _run(["ffmpeg", "-y", "-i", str(source_mp4), "-an", "-c:v", "copy", str(out_mp4)])


def extract_audio_wav(source_mp4: Path, out_wav: Path) -> None:
  out_wav.parent.mkdir(parents=True, exist_ok=True)
  _run([
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
  ])


def wav_to_m4a(wav_path: Path, m4a_path: Path) -> None:
  m4a_path.parent.mkdir(parents=True, exist_ok=True)
  _run([
    "ffmpeg",
    "-y",
    "-i",
    str(wav_path),
    "-c:a",
    "aac",
    "-b:a",
    "192k",
    str(m4a_path),
  ])


def build_multi_audio_mp4(video_only_mp4: Path, stem_m4as: dict[str, Path], out_mp4: Path) -> None:
  """Mux a video-only mp4 with multiple audio tracks.

  stem_m4as must contain exactly the 6 PRD stems.
  """
  out_mp4.parent.mkdir(parents=True, exist_ok=True)
  stem_order = ["vocals", "drums", "bass", "guitar", "piano", "other"]

  cmd: list[str] = ["ffmpeg", "-y", "-i", str(video_only_mp4)]
  for stem in stem_order:
    cmd += ["-i", str(stem_m4as[stem])]

  # Map: first input video, then each audio stream.
  cmd += ["-map", "0:v"]
  for i in range(1, 7):
    cmd += ["-map", f"{i}:a"]

  cmd += ["-c:v", "copy", "-c:a", "copy", "-shortest", str(out_mp4)]
  _run(cmd)
