FROM python:3.11-slim

# System deps: ffmpeg needed for mp4/audio processing.
RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Install uv (preferred Python package manager).
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy project metadata first for better layer caching.
COPY home-agent/pyproject.toml /app/home-agent/pyproject.toml

# Install dependencies (no optional demucs by default).
COPY home-agent/src /app/home-agent/src
RUN cd /app/home-agent \
  && uv pip install --system .

# The agent reads .env from /app/.env by default.
CMD ["python", "-m", "karaoke_agent.cli", "loop"]
