"""Administrative commands for a locally installed Signal Player."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .agent import PlayerAgent
from .version import PLAYER_VERSION


def _health() -> dict | None:
    try:
        with urlopen("http://127.0.0.1:8090/healthz", timeout=2) as response:  # nosec B310: loopback only
            return json.load(response)
    except (OSError, URLError, json.JSONDecodeError):
        return None


def _status(agent: PlayerAgent) -> int:
    health = _health()
    manifest = agent.active_manifest() or {}
    runtime = agent.runtime
    renderer = health.get("renderer", "unknown") if health else runtime.get("renderer", "unknown")
    print(f"Signal Player {PLAYER_VERSION}")
    print()
    print(f"Agent:       {'running' if health else 'not running'}")
    print(f"Renderer:    {renderer}")
    print(f"Enrollment:  {'enrolled' if agent.enrolled else 'not enrolled'}")
    print(f"Server:      {agent.server_url}")
    print(f"Cache:       {runtime.get('cache', 'empty')}")
    print(f"Revision:    {manifest.get('revision', 'none')}")
    return 0


def _clear_cache(agent: PlayerAgent) -> None:
    shutil.rmtree(agent.media_dir, ignore_errors=True)
    agent.runtime["cache"] = "empty"
    agent._save_runtime()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="signal-player", description="Signal Player administration")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("version", help="show player version")
    subcommands.add_parser("status", help="show local player status")
    config = subcommands.add_parser("config", help="view or change player configuration")
    config_commands = config.add_subparsers(dest="config_command", required=True)
    config_commands.add_parser("show", help="show non-secret configuration")
    set_server = config_commands.add_parser("set-server", help="set the Signal server URL")
    set_server.add_argument("server_url")
    subcommands.add_parser("reset-enrollment", help="clear local enrollment while preserving cached signage")
    subcommands.add_parser("clear-cache", help="clear downloaded media while preserving enrollment")
    factory = subcommands.add_parser("factory-reset", help="clear config, enrollment, manifest, and media")
    factory.add_argument("--confirm", metavar="DELETE", required=True, help="must be the word DELETE")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "version":
        print(PLAYER_VERSION)
        return 0
    agent = PlayerAgent()
    if args.command == "status":
        return _status(agent)
    if args.command == "config":
        if args.config_command == "show":
            print(f"server_url = {agent.server_url}")
        else:
            agent.set_server_url(args.server_url)
            print(f"Signal server set to {agent.server_url}")
        return 0
    if args.command == "reset-enrollment":
        agent.reset_enrollment()
        print("Enrollment credentials reset; cached signage was preserved.")
        return 0
    if args.command == "clear-cache":
        _clear_cache(agent)
        print("Downloaded media cache cleared; the next synchronization will refill it.")
        return 0
    if args.confirm != "DELETE":
        print("Refusing factory reset: use --confirm DELETE.", file=sys.stderr)
        return 2
    shutil.rmtree(agent.state_dir, ignore_errors=True)
    agent.config_path.parent.mkdir(parents=True, exist_ok=True)
    agent.config_path.write_text('server_url = "https://signal.example.invalid"\n')
    print("Factory reset completed. Configure a server URL, then enroll this display again.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
