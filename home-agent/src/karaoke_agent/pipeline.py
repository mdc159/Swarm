from __future__ import annotations

import json
import shutil
import signal
import threading
import time
from pathlib import Path

from karaoke_agent.config import Settings
from karaoke_agent.demucs import STEM_IDS, run_demucs
from karaoke_agent.ffmpeg_utils import (
  build_multi_audio_mp4,
  extract_audio_wav,
  extract_video_only,
  get_duration_seconds,
  wav_to_m4a,
)
from karaoke_agent.runpod import RunpodClient
from karaoke_agent.s3 import S3
from karaoke_agent.supabase import Job, Supabase
from karaoke_agent.ytdlp import download_youtube


class KaraokeHomeAgent:
  def __init__(self, settings: Settings) -> None:
    self.settings = settings
    self.settings.ensure_dirs()

    self.supabase = Supabase(settings)
    self.s3 = S3(settings)

    self._shutdown = threading.Event()
    signal.signal(signal.SIGTERM, self._handle_sig)
    signal.signal(signal.SIGINT, self._handle_sig)

    self._lease_thread: threading.Thread | None = None
    self._lease_stop = threading.Event()
    self._lease_job_id: str | None = None

  def close(self) -> None:
    self.supabase.close()

  def _handle_sig(self, _signum: int, _frame) -> None:
    self._shutdown.set()

  def should_split_locally(self, job: Job) -> bool:
    return bool(job.prefer_local_split and self.settings.has_nvidia_gpu and self.settings.demucs_available)

  def _start_lease_renewal(self, job_id: str) -> None:
    self._stop_lease_renewal()
    self._lease_job_id = job_id
    self._lease_stop.clear()

    def loop() -> None:
      while not self._shutdown.is_set() and not self._lease_stop.is_set() and self._lease_job_id == job_id:
        time.sleep(max(30, int(self.settings.lease_seconds / 3)))
        try:
          self.supabase.renew_lease(job_id, self.settings.worker_id, self.settings.lease_seconds)
        except Exception:
          # Lease renewal failures should not crash the worker.
          pass

    self._lease_thread = threading.Thread(target=loop, name=f"lease-{job_id}", daemon=True)
    self._lease_thread.start()

  def _stop_lease_renewal(self) -> None:
    self._lease_stop.set()
    if self._lease_thread and self._lease_thread.is_alive():
      self._lease_thread.join(timeout=5)
    self._lease_thread = None
    self._lease_job_id = None

  def claim_next_job(self) -> Job | None:
    return self.supabase.claim_job(
      worker_id=self.settings.worker_id,
      has_nvidia_gpu=self.settings.has_nvidia_gpu,
      demucs_available=self.settings.demucs_available,
      lease_seconds=self.settings.lease_seconds,
      max_attempts=self.settings.max_attempts,
    )

  def run_once(self) -> bool:
    job = self.claim_next_job()
    if job is None:
      return False

    self._start_lease_renewal(job.job_id)
    try:
      self.process_job(job)
    finally:
      self._stop_lease_renewal()

    return True

  def run_loop(self) -> None:
    while not self._shutdown.is_set():
      did = self.run_once()
      if not did:
        self._shutdown.wait(timeout=self.settings.poll_interval_seconds)

  def process_job(self, job: Job) -> None:
    job_dir = self.settings.download_dir / job.job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    source_mp4 = job_dir / "source.mp4"

    try:
      self.supabase.update_job(job.job_id, "downloading")

      dl = download_youtube(job.source_url, source_mp4)
      duration = get_duration_seconds(dl.video_path)

      # Store best-effort metadata
      extra = {"video_id": dl.video_id, "title": dl.title or job.title, "artist": dl.uploader or job.artist}
      self.supabase.update_job(job.job_id, "downloading", duration_seconds=duration, extra=extra)

      if self.should_split_locally(job):
        self._process_local(job, dl.video_path, duration)
      else:
        self._process_remote(job, dl.video_path)

    except Exception as e:
      self.supabase.update_job(job.job_id, "failed", last_error=str(e))
      raise
    finally:
      shutil.rmtree(job_dir, ignore_errors=True)

  def _process_local(self, job: Job, source_mp4: Path, duration: float) -> None:
    self.supabase.update_job(job.job_id, "processing_local")

    work_dir = Path(self.settings.download_dir) / f"{job.job_id}-local"
    shutil.rmtree(work_dir, ignore_errors=True)
    (work_dir / "tmp").mkdir(parents=True, exist_ok=True)

    audio_wav = work_dir / "tmp" / "audio.wav"
    extract_audio_wav(source_mp4, audio_wav)

    demucs_out = work_dir / "tmp" / "demucs"
    stem_wavs = run_demucs(audio_wav, demucs_out)

    out_dir = work_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)

    # video only
    video_only = out_dir / "video.mp4"
    extract_video_only(source_mp4, video_only)

    # stem m4a
    stem_m4as: dict[str, Path] = {}
    for stem_id in STEM_IDS:
      m4a = out_dir / f"{stem_id}.m4a"
      wav_to_m4a(stem_wavs[stem_id], m4a)
      stem_m4as[stem_id] = m4a

    # stems.json
    stems_json = {
      "title": job.title or "",
      "artist": job.artist or "",
      "duration": duration,
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

    # karaoke_six_stem.mp4
    build_multi_audio_mp4(video_only, stem_m4as, out_dir / "karaoke_six_stem.mp4")

    # Upload to S3 output prefix
    self.s3.upload_tree(out_dir, job.s3_output_prefix)

    self.supabase.update_job(job.job_id, "uploaded_outputs")

    if self.settings.public_base_url:
      public_url = f"{self.settings.public_base_url.rstrip('/')}/{job.s3_output_prefix.rstrip('/')}"
      self.supabase.update_job(job.job_id, "published", public_url=public_url)

  def _process_remote(self, job: Job, source_mp4: Path) -> None:
    # 1) upload source
    self.s3.upload_file(source_mp4, job.s3_input_key, content_type="video/mp4")
    self.supabase.update_job(job.job_id, "uploaded_source")

    # 2) trigger runpod
    if not self.settings.runpod_api_key or not self.settings.runpod_endpoint_id:
      raise RuntimeError("RUNPOD_API_KEY and RUNPOD_ENDPOINT_ID are required for remote split")

    client = RunpodClient(api_key=self.settings.runpod_api_key, endpoint_id=self.settings.runpod_endpoint_id)
    try:
      run = client.run_async(
        {
          "job_id": job.job_id,
          "bucket": self.settings.s3_bucket,
          "input_key": job.s3_input_key,
          "output_prefix": job.s3_output_prefix,
          "model": "htdemucs_6s",
          "create_canonical_mp4": True,
          "metadata": {"title": job.title or "", "artist": job.artist or "", "sourceUrl": job.source_url},
        }
      )
      self.supabase.update_job(job.job_id, "runpod_processing", runpod_job_id=run.id)

      # 3) wait for completion
      st = client.wait_for_completion(
        run.id,
        poll_interval_seconds=self.settings.runpod_poll_interval_seconds,
        timeout_seconds=60 * 60 * 2,
      )

      if st.get("status") != "COMPLETED":
        raise RuntimeError(f"Runpod job failed: {st}")

      self.supabase.update_job(job.job_id, "outputs_ready")

      if self.settings.public_base_url:
        public_url = f"{self.settings.public_base_url.rstrip('/')}/{job.s3_output_prefix.rstrip('/')}"
        self.supabase.update_job(job.job_id, "published", public_url=public_url)

    finally:
      client.close()
