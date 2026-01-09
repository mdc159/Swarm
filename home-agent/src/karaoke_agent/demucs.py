from __future__ import annotations

import subprocess
from pathlib import Path


class DemucsError(RuntimeError):
  pass


STEM_IDS = ["vocals", "drums", "bass", "guitar", "piano", "other"]


def run_demucs(audio_wav: Path, out_dir: Path, model: str = "htdemucs_6s") -> dict[str, Path]:
  """Run Demucs to generate 6 stems.

  Demucs output layout is:
    {out_dir}/separated/{model}/{track_name}/{stem}.wav

  Returns mapping stem_id -> wav path.
  """

  out_dir.mkdir(parents=True, exist_ok=True)

  # Use a stable set of options for reproducibility.
  cmd = [
    "python",
    "-m",
    "demucs",
    "-n",
    model,
    "--out",
    str(out_dir),
    str(audio_wav),
  ]

  proc = subprocess.run(cmd, capture_output=True, text=True)
  if proc.returncode != 0:
    raise DemucsError(proc.stderr or proc.stdout)

  # Locate outputs.
  separated_dir = out_dir / "separated" / model
  # Demucs uses filename stem (without extension) as track dir.
  track_dir = separated_dir / audio_wav.stem
  stems: dict[str, Path] = {}
  for stem_id in STEM_IDS:
    p = track_dir / f"{stem_id}.wav"
    if not p.exists():
      raise DemucsError(f"Missing demucs output: {p}")
    stems[stem_id] = p

  return stems
