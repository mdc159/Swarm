from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from yt_dlp import YoutubeDL


@dataclass(frozen=True)
class DownloadResult:
  video_path: Path
  video_id: str | None
  title: str | None
  uploader: str | None


def download_youtube(url: str, out_path: Path) -> DownloadResult:
  """Download a YouTube URL to a single mp4 file at out_path."""

  out_path.parent.mkdir(parents=True, exist_ok=True)

  ydl_opts = {
    "outtmpl": str(out_path),
    "format": "bv*+ba/b",
    "merge_output_format": "mp4",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
  }

  with YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=True)

  # yt-dlp may change extension based on merge_output_format.
  final_path = out_path
  if not final_path.exists():
    # Try common alternative.
    alt = out_path.with_suffix(".mp4")
    if alt.exists():
      final_path = alt

  return DownloadResult(
    video_path=final_path,
    video_id=info.get("id"),
    title=info.get("title"),
    uploader=info.get("uploader"),
  )
