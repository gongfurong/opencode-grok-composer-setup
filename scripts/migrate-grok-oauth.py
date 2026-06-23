#!/usr/bin/env python3
"""Migrate Grok CLI OAuth credentials to OpenCode auth.json (cross-platform)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

GROK_AUTH_PREFIX = "https://auth.x.ai::"
OPENCODE_PROVIDER_KEY = "xai"


def home() -> Path:
    return Path(os.path.expanduser("~"))


def grok_auth_path() -> Path:
    return home() / ".grok" / "auth.json"


def opencode_auth_path() -> Path:
    return home() / ".local" / "share" / "opencode" / "auth.json"


def find_grok_oauth_entry(grok_auth: dict) -> tuple[str, dict]:
    for key, value in grok_auth.items():
        if key.startswith(GROK_AUTH_PREFIX) and isinstance(value, dict):
            return key, value
    raise RuntimeError(
        "No Grok CLI OAuth entry found. Run `grok login` first, then retry."
    )


def expires_to_ms(expires_at: str) -> int:
    normalized = expires_at.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def main() -> int:
    import argparse

    try:
        from i18n import ensure_utf8_stdio

        ensure_utf8_stdio()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Migrate Grok OAuth to OpenCode")
    parser.add_argument("--quiet", action="store_true", help="Suppress success message")
    args = parser.parse_args()

    grok_path = grok_auth_path()
    opencode_path = opencode_auth_path()

    if not grok_path.is_file():
        print(f"ERROR: Grok CLI auth not found at {grok_path}", file=sys.stderr)
        print("Run `grok login` first.", file=sys.stderr)
        return 1

    grok_auth = load_json(grok_path)
    _, entry = find_grok_oauth_entry(grok_auth)

    access = entry.get("key")
    refresh = entry.get("refresh_token")
    expires_at = entry.get("expires_at")

    if not access or not refresh or not expires_at:
        print("ERROR: Grok OAuth entry is incomplete. Re-run `grok login`.", file=sys.stderr)
        return 1

    opencode_auth = load_json(opencode_path) if opencode_path.is_file() else {}
    opencode_auth[OPENCODE_PROVIDER_KEY] = {
        "type": "oauth",
        "access": access,
        "refresh": refresh,
        "expires": expires_to_ms(expires_at),
    }

    save_json(opencode_path, opencode_auth)

    if not args.quiet:
        print("Migrated Grok CLI OAuth to OpenCode auth.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())