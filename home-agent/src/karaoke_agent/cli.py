from __future__ import annotations

import argparse
import os
import secrets

from karaoke_agent.config import load_settings
from karaoke_agent.pipeline import KaraokeHomeAgent
from karaoke_agent.supabase import Supabase


def _cmd_config_check(args: argparse.Namespace) -> int:
  _ = load_settings(args.env_file)
  return 0


def _cmd_run_once(args: argparse.Namespace) -> int:
  settings = load_settings(args.env_file)
  agent = KaraokeHomeAgent(settings)
  try:
    did = agent.run_once()
    return 0 if did else 2
  finally:
    agent.close()


def _cmd_loop(args: argparse.Namespace) -> int:
  settings = load_settings(args.env_file)
  agent = KaraokeHomeAgent(settings)
  try:
    agent.run_loop()
    return 0
  finally:
    agent.close()


def _cmd_submit(args: argparse.Namespace) -> int:
  settings = load_settings(args.env_file)
  sb = Supabase(settings)
  try:
    job_id = args.job_id or f"job_{secrets.token_hex(8)}"
    row = sb.insert_job(
      job_id=job_id,
      source_url=args.url,
      title=args.title,
      artist=args.artist,
      prefer_local_split=bool(args.prefer_local_split),
    )
    print(row)
    return 0
  finally:
    sb.close()


def main() -> None:
  parser = argparse.ArgumentParser(prog="karaoke-home-agent")
  parser.add_argument("--env-file", default=os.getenv("ENV_FILE"), help="Path to .env file")

  sub = parser.add_subparsers(dest="cmd", required=True)

  p = sub.add_parser("config-check")
  p.set_defaults(func=_cmd_config_check)

  p = sub.add_parser("once")
  p.set_defaults(func=_cmd_run_once)

  p = sub.add_parser("loop")
  p.set_defaults(func=_cmd_loop)

  p = sub.add_parser("submit")
  p.add_argument("--url", required=True)
  p.add_argument("--title")
  p.add_argument("--artist")
  p.add_argument("--prefer-local-split", action="store_true")
  p.add_argument("--job-id")
  p.set_defaults(func=_cmd_submit)

  args = parser.parse_args()
  rc = args.func(args)
  raise SystemExit(rc)


if __name__ == "__main__":
  main()
