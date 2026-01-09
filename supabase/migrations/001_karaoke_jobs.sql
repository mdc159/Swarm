-- Swarm Karaoke Pipeline - core job tracking
--
-- Creates:
-- - karaoke_jobs table (PRD)
-- - karaoke_library view
-- - updated_at trigger
-- - RPC functions for atomic leasing + lease renewal

create extension if not exists pgcrypto;

create table if not exists public.karaoke_jobs (
  id uuid primary key default gen_random_uuid(),
  job_id text unique not null,

  -- Metadata
  title text,
  artist text,
  slug text unique,
  source_url text not null,
  video_id text,

  -- Processing options
  source_type text check (source_type in ('youtube', 'upload')) default 'youtube',
  prefer_local_split boolean default false,

  -- Status tracking
  processing_status text check (processing_status in (
    'queued',
    'leased',
    'downloading',
    'processing_local',
    'uploaded_source',
    'uploaded_outputs',
    'runpod_processing',
    'outputs_ready',
    'publishing',
    'published',
    'failed'
  )) default 'queued',

  -- Worker coordination
  lease_owner text,
  lease_until timestamptz,
  attempts integer default 0,
  last_error text,

  -- Output
  duration integer,
  public_url text,
  runpod_job_id text,

  -- Timestamps
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Keep updated_at current
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_karaoke_jobs_updated_at on public.karaoke_jobs;
create trigger trg_karaoke_jobs_updated_at
before update on public.karaoke_jobs
for each row
execute function public.set_updated_at();

-- Published-only view
create or replace view public.karaoke_library as
select id, job_id, title, artist, slug, duration, public_url, created_at
from public.karaoke_jobs
where processing_status = 'published'
order by created_at desc;

-- -----------------------------------------------------------------------------
-- RPC: claim_karaoke_job
--
-- Atomically:
-- 1) re-queues expired leases
-- 2) picks a single available job
-- 3) marks it leased and extends lease_until
--
-- The worker can pass capabilities so we can prioritize prefer_local_split jobs
-- when the worker is able to run local splitting.
-- -----------------------------------------------------------------------------
create or replace function public.claim_karaoke_job(
  worker_id text,
  has_nvidia_gpu boolean default false,
  demucs_available boolean default false,
  lease_seconds integer default 900,
  max_attempts integer default 3
)
returns setof public.karaoke_jobs
language plpgsql
security definer
as $$
declare
  v_can_local boolean := (coalesce(has_nvidia_gpu, false) and coalesce(demucs_available, false));
begin
  -- 1) Re-queue expired leases
  update public.karaoke_jobs
    set processing_status = 'queued',
        lease_owner = null,
        lease_until = null
  where processing_status = 'leased'
    and lease_until is not null
    and lease_until < now();

  -- 2) Claim one job
  return query
  with candidate as (
    select id
    from public.karaoke_jobs
    where processing_status in ('queued', 'failed')
      and coalesce(attempts, 0) < max_attempts
    order by
      case when v_can_local then (case when prefer_local_split then 0 else 1 end) else 0 end,
      created_at asc
    for update skip locked
    limit 1
  )
  update public.karaoke_jobs j
    set processing_status = 'leased',
        lease_owner = worker_id,
        lease_until = now() + make_interval(secs => lease_seconds),
        attempts = coalesce(j.attempts, 0) + 1
  from candidate
  where j.id = candidate.id
  returning j.*;
end;
$$;

-- RPC: renew lease
create or replace function public.renew_karaoke_job_lease(
  job_id text,
  worker_id text,
  lease_seconds integer default 900
)
returns boolean
language plpgsql
security definer
as $$
begin
  update public.karaoke_jobs
    set lease_until = now() + make_interval(secs => lease_seconds)
  where public.karaoke_jobs.job_id = renew_karaoke_job_lease.job_id
    and lease_owner = renew_karaoke_job_lease.worker_id
    and processing_status = 'leased';

  return found;
end;
$$;
