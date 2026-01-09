# Karaoke Pipeline PRD

A clean rebuild of the distributed karaoke processing system.

## Problem Statement

Build a karaoke creation pipeline that:
1. Downloads YouTube videos (requires residential IP - datacenter IPs are blocked)
2. Separates audio into 6 stems (vocals, drums, bass, guitar, piano, other)
3. Publishes assets for web-based stem mixing

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   User / UI     │────▶│    VPS (n8n)    │────▶│    Supabase     │
│   Submit URL    │     │    Orchestrator │     │    Job Queue    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                        ┌───────────────────────────────┘
                        ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Home Agent    │────▶│   Runpod S3     │◀────│   Runpod GPU    │
│   (Linux PC)    │     │   (Storage)     │     │   (Optional)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Components

### 1. VPS (Orchestrator)
- **Role**: API gateway, workflow orchestration, static file serving
- **Services**: n8n (workflows), NGINX (static files)
- **Cannot**: Download from YouTube (IP blocked), run GPU workloads

### 2. Supabase (Database)
- **Role**: Job queue, status tracking, library storage
- **Table**: `karaoke_jobs` - Job queue with status machine
- **View**: `karaoke_library` - Published tracks only

### 3. Home Agent (Worker)
- **Role**: YouTube downloads + optional local stem separation
- **Must have**: Residential IP (for YouTube), Python 3, yt-dlp, boto3
- **Optional**: NVIDIA GPU + Demucs for local processing

### 4. Runpod (GPU Processing)
- **Role**: Remote stem separation when home agent lacks GPU
- **S3 Storage**: Input/output staging area
- **Serverless GPU**: Demucs htdemucs_6s model

## The Split Decision

The home agent decides how to process stems based on configuration and capabilities:

```python
def should_split_locally(job, worker):
    """Decide whether to split stems locally or use Runpod."""
    return (
        job.prefer_local_split and
        worker.has_nvidia_gpu and
        worker.demucs_available
    )
```

### Path A: Local Split (Free)
When `should_split_locally() == True`:
1. Download video with yt-dlp
2. Run Demucs locally (htdemucs_6s model)
3. Upload all output artifacts directly to S3 output directory
4. Status: `downloading` → `processing_local` → `uploaded_outputs`

### Path B: Remote Split (Paid)
When `should_split_locally() == False`:
1. Download video with yt-dlp
2. Upload source video to S3 input directory
3. Trigger Runpod serverless job
4. Runpod processes and uploads to S3 output directory
5. Status: `downloading` → `uploaded_source` → `runpod_processing` → `outputs_ready`

## Database Schema

### Table: `karaoke_jobs`

```sql
CREATE TABLE karaoke_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id TEXT UNIQUE NOT NULL,
  
  -- Metadata
  title TEXT,
  artist TEXT,
  slug TEXT UNIQUE,
  source_url TEXT NOT NULL,
  video_id TEXT,
  
  -- Processing options
  source_type TEXT CHECK (source_type IN ('youtube', 'upload')) DEFAULT 'youtube',
  prefer_local_split BOOLEAN DEFAULT false,
  
  -- Status tracking
  processing_status TEXT CHECK (processing_status IN (
    'queued',           -- Waiting for worker
    'leased',           -- Claimed by worker
    'downloading',      -- Downloading from YouTube
    'processing_local', -- Running Demucs locally
    'uploaded_source',  -- Source uploaded, awaiting Runpod
    'uploaded_outputs', -- Local split complete
    'runpod_processing',-- Runpod processing
    'outputs_ready',    -- Ready for publishing
    'publishing',       -- Deploying to VPS
    'published',        -- Complete
    'failed'            -- Error occurred
  )) DEFAULT 'queued',
  
  -- Worker coordination
  lease_owner TEXT,
  lease_until TIMESTAMPTZ,
  attempts INTEGER DEFAULT 0,
  last_error TEXT,
  
  -- Output
  duration INTEGER,
  public_url TEXT,
  
  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### View: `karaoke_library`

```sql
CREATE VIEW karaoke_library AS
SELECT id, job_id, title, artist, slug, duration, public_url, created_at
FROM karaoke_jobs
WHERE processing_status = 'published'
ORDER BY created_at DESC;
```

## API Contracts

### POST /webhook/karaoke-submit
Submit a YouTube URL for processing.

```json
// Request
{
  "url": "https://youtube.com/watch?v=...",
  "title": "Song Title",
  "artist": "Artist Name",
  "prefer_local_split": false
}

// Response 202
{
  "jobId": "job_abc123",
  "status": "queued"
}
```

### POST /webhook/worker/claim
Home agent claims next available job.

```json
// Request
{
  "worker_id": "home-agent-1",
  "has_nvidia_gpu": true,
  "demucs_available": true
}

// Response 200
{
  "jobId": "job_abc123",
  "sourceUrl": "https://youtube.com/...",
  "preferLocalSplit": false,
  "s3InputKey": "karaoke/in/job_abc123/source.mp4",
  "s3OutputPrefix": "karaoke/out/job_abc123/"
}
```

### POST /webhook/worker/update
Update job status.

```json
// Request
{
  "jobId": "job_abc123",
  "status": "uploaded_outputs",
  "s3Key": "karaoke/out/job_abc123/"
}
```

### GET /webhook/karaoke-library
List published tracks.

```json
// Response 200
{
  "tracks": [
    {
      "title": "Song Title",
      "artist": "Artist",
      "slug": "song-title",
      "duration": 180,
      "publicUrl": "https://karaoke.example.com/videos/song-title/"
    }
  ]
}
```

## S3 Directory Structure

```
karaoke/
├── in/{job_id}/
│   └── source.mp4           # Input from home agent (remote path)
│
└── out/{job_id}/
    ├── karaoke_six_stem.mp4  # Video + 6 audio tracks
    ├── video.mp4             # Video only
    ├── vocals.m4a            # Stem files
    ├── drums.m4a
    ├── bass.m4a
    ├── guitar.m4a
    ├── piano.m4a
    ├── other.m4a
    └── stems.json            # Manifest
```

## Output Artifacts

### karaoke_six_stem.mp4
Single MP4 with 1 video track + 6 AAC audio tracks.

### Web Mixer Assets
- `video.mp4` - Video only (H.264)
- `{stem}.m4a` - Individual stems (AAC 192kbps)
- `stems.json` - Manifest for UI

### stems.json Schema

```json
{
  "title": "Song Title",
  "artist": "Artist Name",
  "duration": 180.5,
  "video": "video.mp4",
  "stems": [
    {"id": "vocals", "name": "Vocals", "file": "vocals.m4a"},
    {"id": "drums", "name": "Drums", "file": "drums.m4a"},
    {"id": "bass", "name": "Bass", "file": "bass.m4a"},
    {"id": "guitar", "name": "Guitar", "file": "guitar.m4a"},
    {"id": "piano", "name": "Piano", "file": "piano.m4a"},
    {"id": "other", "name": "Other", "file": "other.m4a"}
  ]
}
```

## Home Agent Implementation

### Core Flow

```python
class KaraokeAgent:
    def process_job(self, job):
        # 1. Download video
        self.update_status(job.id, "downloading")
        video_path = self.download_video(job.source_url)
        
        # 2. Decide split path
        if self.should_split_locally(job):
            self.process_local(job, video_path)
        else:
            self.process_remote(job, video_path)
    
    def should_split_locally(self, job):
        return (
            job.prefer_local_split and
            self.config.has_nvidia_gpu and
            self.config.demucs_available
        )
    
    def process_local(self, job, video_path):
        """Free path - run Demucs locally."""
        self.update_status(job.id, "processing_local")
        
        # Run Demucs
        stems = self.run_demucs(video_path)
        
        # Create output artifacts
        self.create_six_stem_mp4(video_path, stems)
        self.create_web_assets(video_path, stems)
        
        # Upload directly to output location
        self.upload_outputs(job.id, job.s3_output_prefix)
        self.update_status(job.id, "uploaded_outputs")
    
    def process_remote(self, job, video_path):
        """Paid path - upload for Runpod processing."""
        # Upload source
        self.upload_file(video_path, job.s3_input_key)
        self.update_status(job.id, "uploaded_source")
        # Runpod takes over from here
```

### Worker Configuration

```bash
# Required
VPS_API_BASE=https://n8n.example.com/webhook
WORKER_TOKEN=secret_token
WORKER_ID=home-agent-1
POLL_INTERVAL=30
DOWNLOAD_DIR=/var/lib/karaoke-agent/spool

# S3
S3_ENDPOINT=https://s3.example.com
S3_BUCKET=karaoke
S3_ACCESS_KEY=...
S3_SECRET_KEY=...

# Optional - for local split
HAS_NVIDIA_GPU=true
DEMUCS_AVAILABLE=true
```

## VPS Directory Structure

```
/var/www/karaoke/videos/{slug}/
├── karaoke_six_stem.mp4
├── video.mp4
├── vocals.m4a
├── drums.m4a
├── bass.m4a
├── guitar.m4a
├── piano.m4a
├── other.m4a
└── stems.json
```

## Repository Structure

```
swarm/
├── README.md
├── docker-compose.yml        # Local development
├── .env.example              # Environment template
│
├── home-agent/               # Python worker
│   ├── pyproject.toml
│   ├── src/
│   │   └── karaoke_agent/
│   │       ├── agent.py      # Main worker
│   │       ├── config.py     # Pydantic settings
│   │       ├── demucs.py     # Local stem separation
│   │       ├── s3.py         # S3 operations
│   │       └── ytdlp.py      # YouTube downloads
│   ├── systemd/
│   │   └── karaoke-agent.service
│   └── README.md
│
├── runpod-worker/            # GPU serverless worker
│   ├── Dockerfile
│   ├── handler.py
│   ├── requirements.txt
│   └── README.md
│
├── n8n-workflows/            # Workflow definitions
│   ├── karaoke-submit.json
│   ├── worker-claim.json
│   ├── worker-update.json
│   ├── karaoke-library.json
│   └── karaoke-publish.json
│
├── supabase/                 # Database migrations
│   └── migrations/
│       └── 001_karaoke_jobs.sql
│
└── docs/
    └── DEPLOYMENT.md
```

## Acceptance Criteria

### Must Work
- [ ] Submit YouTube URL → job created in Supabase
- [ ] Home agent claims job and downloads video
- [ ] Local split path: Demucs runs locally when configured
- [ ] Remote split path: Source uploaded, Runpod processes
- [ ] VPS publishes assets to static directory
- [ ] Job status tracks through state machine
- [ ] Library API returns published tracks

### Quality Requirements
- [ ] Graceful shutdown on SIGTERM
- [ ] Lease expiry re-queues stuck jobs
- [ ] Failed jobs record last_error
- [ ] Max 3 retry attempts
- [ ] Home agent auto-restarts via systemd

## Environment Variables

### Single .env File

```bash
# === VPS/n8n ===
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
WORKER_TOKEN=shared-worker-secret

# === S3 (Runpod Network Volume) ===
S3_ENDPOINT=https://s3api.runpod.io
S3_BUCKET=your-bucket
S3_ACCESS_KEY=your-key
S3_SECRET_KEY=your-secret

# === Home Agent ===
WORKER_ID=home-agent-1
POLL_INTERVAL=30
DOWNLOAD_DIR=/var/lib/karaoke-agent/spool
HAS_NVIDIA_GPU=false
DEMUCS_AVAILABLE=false

# === Runpod ===
RUNPOD_API_KEY=your-runpod-key
RUNPOD_ENDPOINT_ID=your-endpoint-id
```

## Notes for Implementation

1. **Home Agent** is the critical component - must work with residential IP
2. **Local split** is optional but saves money - make it easy to enable/disable
3. **Status machine** is strict - transitions must be validated
4. **Lease renewal** prevents stuck jobs from blocking the queue
5. **All outputs** go through S3, then VPS pulls from S3 for publishing
