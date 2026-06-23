#!/usr/bin/env python3
"""
Sync latest Grok Build + Composer models from Grok CLI into OpenCode.

Source of truth: Grok Build (models_cache.json, config.toml, `grok models`).
Target: OpenCode (opencode.json). Registers Grok models via config + OAuth.
Uses `opencode models xai` only when available to refine aliases (e.g. grok-build
→ grok-build-0.1); otherwise writes Grok model IDs directly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from i18n import I18n, add_lang_argument, ensure_utf8_stdio, resolve_lang

PROVIDER = "xai"
COMPOSER_FAMILY = "composer"
BUILD_FAMILY = "build"
GROK_MODELS_CACHE = "models_cache.json"
GROK_CONFIG = "config.toml"


def home() -> Path:
    return Path(os.path.expanduser("~"))


def display_path(path: str | Path | None) -> str | None:
    if not path:
        return None
    text = str(path)
    home_str = str(home())
    if text.startswith(home_str):
        return "~" + text[len(home_str) :].replace("\\", "/")
    return text.replace("\\", "/")


def grok_dir() -> Path:
    return home() / ".grok"


def opencode_config_path() -> Path:
    return home() / ".config" / "opencode" / "opencode.json"


def run_command(cmd: list[str]) -> str:
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return result.stdout


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def version_key(model_id: str) -> tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", model_id)]
    return tuple(nums) if nums else (0,)


def family_of(model_id: str) -> str | None:
    if "composer" in model_id:
        return COMPOSER_FAMILY
    if model_id == "grok-build" or model_id.startswith("grok-build"):
        return BUILD_FAMILY
    return None


def prefer_fast(models: list[str]) -> str:
    fast = [m for m in models if "fast" in m.lower()]
    pool = fast or models
    return max(pool, key=lambda m: (version_key(m), m))


def pick_latest_in_family(model_ids: list[str], family: str) -> str | None:
    if family == COMPOSER_FAMILY:
        matched = [m for m in model_ids if family_of(m) == COMPOSER_FAMILY]
        return prefer_fast(matched) if matched else None
    if family == BUILD_FAMILY:
        matched = [m for m in model_ids if family_of(m) == BUILD_FAMILY]
        return max(matched, key=lambda m: (version_key(m), m)) if matched else None
    return None


def configured_in_family(configured: dict[str, Any], family: str) -> str | None:
    matched = [m for m in configured if family_of(m) == family]
    if not matched:
        return None
    return max(matched, key=lambda m: (version_key(m), m))


def parse_grok_config(config_path: Path) -> dict[str, str]:
    if not config_path.is_file():
        return {}
    try:
        import tomllib

        with config_path.open("rb") as f:
            data = tomllib.load(f)
        models = data.get("models", {})
        ui = data.get("ui", {})
        out: dict[str, str] = {}
        if isinstance(models.get("default"), str):
            out["default"] = models["default"]
        if isinstance(ui.get("fork_secondary_model"), str):
            out["secondary"] = ui["fork_secondary_model"]
        return out
    except Exception:
        text = config_path.read_text(encoding="utf-8")
        out: dict[str, str] = {}
        for key, section in (("default", "models"), ("secondary", "ui")):
            pattern = (
                rf"\[{section}\][^\[]*?"
                rf"{'fork_secondary_model' if key == 'secondary' else 'default'}"
                r'\s*=\s*"([^"]+)"'
            )
            match = re.search(pattern, text, re.DOTALL)
            if match:
                out[key] = match.group(1)
        return out


def parse_grok_models_cli(stdout: str) -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    default_id: str | None = None
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("Default model:"):
            default_id = stripped.split(":", 1)[1].strip()
            continue
        match = re.match(r"^[*-]\s+(\S+)(?:\s+\(default\))?$", stripped)
        if match:
            model_id = match.group(1)
            models.append(
                {
                    "id": model_id,
                    "name": model_id,
                    "is_default": "(default)" in stripped or model_id == default_id,
                }
            )
    return models


def load_grok_models() -> dict[str, Any]:
    cache_path = grok_dir() / GROK_MODELS_CACHE
    config_path = grok_dir() / GROK_CONFIG
    source = "none"
    models: list[dict[str, Any]] = []

    if cache_path.is_file():
        cache = load_json(cache_path)
        for model_id, entry in cache.get("models", {}).items():
            info = entry.get("info", {}) if isinstance(entry, dict) else {}
            models.append(
                {
                    "id": model_id,
                    "name": info.get("name") or model_id,
                    "agent_type": info.get("agent_type"),
                    "description": info.get("description"),
                }
            )
        source = "models_cache.json"

    if not models:
        try:
            stdout = run_command(["grok", "models"])
            models = parse_grok_models_cli(stdout)
            source = "grok models"
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    grok_config = parse_grok_config(config_path)
    default_grok = grok_config.get("default")
    if not default_grok and models:
        flagged = [m["id"] for m in models if m.get("is_default")]
        default_grok = flagged[0] if flagged else None

    return {
        "source": source,
        "config_path": display_path(config_path),
        "cache_path": display_path(cache_path) if cache_path.is_file() else None,
        "config": grok_config,
        "default": default_grok,
        "model_ids": [m["id"] for m in models],
        "models": models,
    }


def load_opencode_models() -> dict[str, Any]:
    ids: list[str] = []
    try:
        stdout = run_command(["opencode", "models", PROVIDER])
    except (subprocess.CalledProcessError, FileNotFoundError):
        stdout = ""

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(f"{PROVIDER}/"):
            ids.append(line.split("/", 1)[1])
        elif family_of(line):
            ids.append(line)

    config_path = opencode_config_path()
    current_default = None
    configured_models: dict[str, Any] = {}
    if config_path.is_file():
        config = load_json(config_path)
        current_default = config.get("model")
        configured_models = (
            config.get("provider", {})
            .get(PROVIDER, {})
            .get("models", {})
        )

    return {
        "config_path": display_path(config_path),
        "default": current_default,
        "model_ids": ids,
        "configured_models": configured_models,
    }


def resolve_grok_to_opencode(grok_id: str, opencode_ids: list[str]) -> dict[str, Any]:
    family = family_of(grok_id)
    if grok_id in opencode_ids:
        return {
            "grok_id": grok_id,
            "opencode_id": grok_id,
            "match": "exact",
            "family": family,
        }

    if family == BUILD_FAMILY:
        candidates = [m for m in opencode_ids if family_of(m) == BUILD_FAMILY]
        if candidates:
            resolved = max(candidates, key=lambda m: (version_key(m), m))
            return {
                "grok_id": grok_id,
                "opencode_id": resolved,
                "match": "family-latest",
                "family": family,
            }
        return {
            "grok_id": grok_id,
            "opencode_id": grok_id,
            "match": "grok-register",
            "family": family,
        }

    if family == COMPOSER_FAMILY:
        candidates = [m for m in opencode_ids if family_of(m) == COMPOSER_FAMILY]
        if candidates:
            grok_ver = version_key(grok_id)
            newer = [m for m in candidates if version_key(m) >= grok_ver]
            pool = newer or candidates
            resolved = prefer_fast(pool)
            match = "version-upgrade" if resolved != grok_id else "family-latest"
            return {
                "grok_id": grok_id,
                "opencode_id": resolved,
                "match": match,
                "family": family,
            }
        return {
            "grok_id": grok_id,
            "opencode_id": grok_id,
            "match": "grok-register",
            "family": family,
        }

    return {
        "grok_id": grok_id,
        "opencode_id": None,
        "match": "unresolved",
        "family": family,
        "reason": "unsupported model family",
    }


def display_name(model_id: str, grok_name: str | None = None) -> str:
    if grok_name and grok_name != model_id:
        return grok_name
    if family_of(model_id) == COMPOSER_FAMILY:
        suffix = model_id.split("grok-composer-", 1)[-1]
        return "Composer " + suffix.replace("-", " ").title()
    if family_of(model_id) == BUILD_FAMILY:
        return "Grok Build"
    return model_id


def sync_plan(grok: dict[str, Any], opencode: dict[str, Any]) -> dict[str, Any]:
    grok_ids = grok["model_ids"]
    opencode_ids = opencode["model_ids"]

    grok_composer = pick_latest_in_family(grok_ids, COMPOSER_FAMILY)
    grok_build = pick_latest_in_family(grok_ids, BUILD_FAMILY)

    resolved: dict[str, Any] = {}
    if grok_composer:
        resolved["composer"] = resolve_grok_to_opencode(grok_composer, opencode_ids)
    if grok_build:
        resolved["build"] = resolve_grok_to_opencode(grok_build, opencode_ids)

    grok_name_by_id = {m["id"]: m.get("name", m["id"]) for m in grok["models"]}

    for key in list(resolved.keys()):
        entry = resolved[key]
        opencode_id = entry.get("opencode_id")
        grok_id = entry.get("grok_id")
        entry["full"] = f"{PROVIDER}/{opencode_id}" if opencode_id else None
        entry["name"] = (
            display_name(opencode_id, grok_name_by_id.get(grok_id))
            if opencode_id
            else None
        )

    default_grok = grok.get("default")
    default_resolution = None
    if default_grok:
        default_resolution = resolve_grok_to_opencode(default_grok, opencode_ids)

    default_opencode = (
        default_resolution.get("opencode_id")
        if default_resolution and default_resolution.get("opencode_id")
        else (resolved.get("composer") or resolved.get("build") or {}).get("opencode_id")
    )
    default_full = f"{PROVIDER}/{default_opencode}" if default_opencode else None

    changes: dict[str, Any] = {}
    # OpenCode top-level `model` is NOT synced by default — preserve user's last choice.

    configured = opencode.get("configured_models", {})
    comparison: dict[str, Any] = {}

    for key, entry in resolved.items():
        opencode_id = entry.get("opencode_id")
        grok_id = entry.get("grok_id")
        if not opencode_id:
            comparison[key] = {
                "status": "unresolved",
                "grok_id": grok_id,
                "opencode_id": None,
                "configured": False,
                "reason": entry.get("reason"),
                "match": entry.get("match"),
            }
            continue

        family = family_of(opencode_id) or key
        previous_id = configured_in_family(configured, family)
        is_target_configured = opencode_id in configured

        if previous_id and previous_id != opencode_id:
            changes[f"upgrade_model_{key}"] = {
                "from": previous_id,
                "to": opencode_id,
                "family": family,
            }
            item_status = "outdated"
        elif not is_target_configured:
            changes[f"add_model_{key}"] = opencode_id
            item_status = "missing"
        else:
            item_status = "ok"

        comparison[key] = {
            "status": item_status,
            "grok_id": grok_id,
            "opencode_id": opencode_id,
            "opencode_full": entry.get("full"),
            "previous_opencode_id": previous_id,
            "configured": is_target_configured,
            "match": entry.get("match"),
        }

    ready = all(entry.get("opencode_id") for entry in resolved.values()) if resolved else False
    has_any_configured = bool(configured)

    if not ready:
        sync_status = "unresolved"
        action = "fix_mapping"
    elif not has_any_configured and changes:
        sync_status = "not_configured"
        action = "write_config"
    elif changes:
        sync_status = "outdated"
        action = "write_config"
    else:
        sync_status = "synced"
        action = "skip"

    comparison["default_model"] = {
        "status": "preserved",
        "managed": False,
        "grok_default": default_grok,
        "grok_default_full": default_full,
        "opencode_current": opencode.get("default"),
        "note": "OpenCode default is not changed by sync; user keeps last-selected model",
    }

    return {
        "sync_direction": "grok-build -> opencode",
        "grok": {
            "source": grok["source"],
            "config_path": grok["config_path"],
            "cache_path": grok.get("cache_path"),
            "default": grok.get("default"),
            "secondary": grok.get("config", {}).get("secondary"),
            "model_ids": grok_ids,
            "selected": {
                "composer": grok_composer,
                "build": grok_build,
            },
        },
        "opencode": {
            "config_path": opencode["config_path"],
            "default": opencode.get("default"),
            "model_ids": opencode_ids,
            "configured_models": list(opencode.get("configured_models", {}).keys()),
        },
        "resolved": resolved,
        "default_model": default_full,
        "default_resolution": default_resolution,
        "comparison": comparison,
        "status": sync_status,
        "action": action,
        "changes": changes,
        "ready": ready,
    }


def build_outcome(
    plan: dict[str, Any], applied: bool, dry_run: bool, i18n: I18n
) -> dict[str, Any]:
    status = plan.get("status", "unknown")
    changes = plan.get("changes") or {}
    comparison = plan.get("comparison") or {}

    models_current = []
    for family in ("composer", "build"):
        item = comparison.get(family, {})
        if item.get("opencode_id"):
            models_current.append(
                {
                    "family": family,
                    "grok_id": item.get("grok_id"),
                    "opencode_id": item.get("opencode_id"),
                    "opencode_full": item.get("opencode_full"),
                }
            )

    default_cmp = comparison.get("default_model", {})
    upgrades: list[dict[str, Any]] = []
    for key, value in changes.items():
        if key.startswith("upgrade_model_") and isinstance(value, dict):
            upgrades.append(
                {
                    "family": value.get("family") or key.replace("upgrade_model_", ""),
                    "from": value.get("from"),
                    "to": value.get("to"),
                }
            )

    if status == "unresolved":
        unresolved = [
            comparison[k]
            for k in ("composer", "build")
            if comparison.get(k, {}).get("status") == "unresolved"
        ]
        return {
            "type": "failed",
            "headline": i18n.t("outcome.failed"),
            "applied": False,
            "unresolved": unresolved,
        }

    if status == "synced":
        return {
            "type": "no_change",
            "headline": i18n.t("outcome.no_change"),
            "applied": False,
            "models": models_current,
            "default_model": plan.get("default_model"),
        }

    if dry_run:
        outcome_type = "preview_configure" if status == "not_configured" else "preview_update"
        return {
            "type": outcome_type,
            "headline": i18n.t(f"outcome.{outcome_type}"),
            "applied": False,
            "models": models_current,
            "default_model": plan.get("default_model"),
            "upgrades": upgrades,
            "changes": changes,
        }

    if status == "not_configured":
        return {
            "type": "configured",
            "headline": i18n.t("outcome.configured"),
            "applied": applied,
            "models": models_current,
            "default_model": plan.get("default_model"),
            "changes": changes,
        }

    return {
        "type": "updated",
        "headline": i18n.t("outcome.updated"),
        "applied": applied,
        "models": models_current,
        "default_model": plan.get("default_model"),
        "upgrades": upgrades,
        "changes": changes,
    }


def format_outcome_report(
    plan: dict[str, Any], i18n: I18n, *, quiet: bool = True
) -> str:
    outcome = plan.get("outcome") or {}
    headline = outcome.get("headline", outcome.get("type", "unknown"))
    if quiet and outcome.get("type") != "failed":
        return ""
    if outcome.get("type") == "failed":
        lines = [i18n.t("ui.done_fail", summary=headline), i18n.t("sync.failed_intro")]
        for item in outcome.get("unresolved") or []:
            lines.append(f"  - {item.get('grok_id')}: {i18n.t('sync.unresolved')}")
        lines.append(i18n.t("sync.failed_tip"))
        return "\n".join(lines)
    return i18n.t("ui.done_ok", summary=headline)


def format_comparison_report(plan: dict[str, Any], i18n: I18n) -> str:
    lines: list[str] = []
    status = plan.get("status", "unknown")
    status_label = i18n.t(f"compare.status.{status}") if status in (
        "synced", "outdated", "not_configured", "unresolved"
    ) else status

    lines.append("=" * 60)
    lines.append(i18n.t("compare.title"))
    lines.append("=" * 60)
    lines.append("")
    lines.append(f"sync: {plan.get('sync_direction')} | status: {status} — {status_label}")
    lines.append(f"action: {plan.get('action')}")
    lines.append("")

    grok = plan.get("grok", {})
    opencode = plan.get("opencode", {})
    lines.append("[Grok Build]")
    lines.append(f"  source:   {grok.get('source')}")
    lines.append(f"  config:   {grok.get('config_path')}")
    lines.append(f"  default:  {grok.get('default')}")
    lines.append(f"  composer: {grok.get('selected', {}).get('composer')}")
    lines.append(f"  build:    {grok.get('selected', {}).get('build')}")
    lines.append("")

    lines.append("[OpenCode]")
    lines.append(f"  config:   {opencode.get('config_path')}")
    configured = opencode.get("configured_models") or []
    lines.append(
        f"  models:   {', '.join(configured) if configured else i18n.t('none')}"
    )
    lines.append("")

    lines.append("[Mapping]")
    for family in ("composer", "build"):
        item = plan.get("comparison", {}).get(family, {})
        if not item:
            continue
        st = item.get("status", "-")
        st_label = i18n.t(f"compare.map.{st}") if st in ("ok", "missing", "unresolved") else st
        lines.append(
            f"  {family}: {item.get('grok_id')} → {item.get('opencode_id')} "
            f"({i18n.yes_no(item.get('configured'))}, {st_label})"
        )
    lines.append("")

    changes = plan.get("changes") or {}
    if changes:
        lines.append("[Pending changes]")
        for key, value in changes.items():
            lines.append(f"  - {key}: {value}")
    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def apply_plan(
    plan: dict[str, Any],
    config_path: Path,
    set_default: str = "preserve",
) -> dict:
    config = load_json(config_path) if config_path.is_file() else {}
    provider = config.setdefault("provider", {})
    xai = provider.setdefault(PROVIDER, {})
    models = xai.setdefault("models", {})

    for key in ("composer", "build"):
        entry = plan.get("resolved", {}).get(key)
        if not entry or not entry.get("opencode_id"):
            continue
        model_id = entry["opencode_id"]
        models[model_id] = {"name": entry.get("name") or display_name(model_id)}

    if set_default != "preserve":
        chosen = plan.get("default_model")
        if set_default == "build":
            build_full = plan.get("resolved", {}).get("build", {}).get("full")
            if build_full:
                chosen = build_full
        elif set_default == "composer":
            composer_full = plan.get("resolved", {}).get("composer", {}).get("full")
            if composer_full:
                chosen = composer_full
        if chosen:
            config["model"] = chosen

    config["$schema"] = config.get("$schema", "https://opencode.ai/config.json")
    save_json(config_path, config)
    return config


def main() -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Sync Grok Build models/config into OpenCode (grok -> opencode)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview sync result without writing opencode.json",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed comparison and outcome",
    )
    parser.add_argument(
        "--write-config",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--config",
        default=str(opencode_config_path()),
        help="Path to opencode.json",
    )
    parser.add_argument(
        "--set-default",
        choices=["preserve", "grok", "composer", "build"],
        default="preserve",
        help="OpenCode top-level model: preserve (default, do not change), or set from grok/composer/build",
    )
    parser.add_argument("--emit-result", action="store_true", help=argparse.SUPPRESS)
    add_lang_argument(parser)
    args = parser.parse_args()
    lang = resolve_lang(args.lang, user_text=args.user_message)
    i18n = I18n(lang)

    def _emit(payload: dict[str, Any]) -> None:
        if args.emit_result:
            print(f"SYNC_RESULT:{json.dumps(payload, ensure_ascii=False)}", flush=True)

    try:
        grok = load_grok_models()
        opencode = load_opencode_models()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        _emit({"exit_code": 1, "status": "error", "error": str(exc)})
        return 1

    if not grok["model_ids"]:
        err = (
            "No Grok Build models found. Run `grok models` or ensure "
            f"{GROK_MODELS_CACHE} exists under ~/.grok/"
        )
        print(f"ERROR: {err}", file=sys.stderr)
        _emit({"exit_code": 1, "status": "error", "error": err})
        return 1

    plan = sync_plan(grok, opencode)
    set_default = args.set_default
    dry_run = args.dry_run
    applied = False

    quiet = not args.verbose
    if args.verbose:
        print(format_comparison_report(plan, i18n))
        print("")

    should_write = not dry_run and plan.get("action") == "write_config"
    if should_write:
        if not plan["ready"]:
            plan["outcome"] = build_outcome(plan, applied=False, dry_run=False, i18n=i18n)
            text = format_outcome_report(plan, i18n, quiet=False)
            if text:
                print(text)
            print("\nERROR: Cannot write config — unresolved model mappings.", file=sys.stderr)
            _emit(sync_result_payload(plan, 1, "unresolved model mappings"))
            return 1
        apply_plan(plan, Path(args.config), set_default=set_default)
        applied = True

    plan["outcome"] = build_outcome(plan, applied=applied, dry_run=dry_run, i18n=i18n)
    plan["lang"] = lang
    text = format_outcome_report(plan, i18n, quiet=quiet)
    if text:
        print(text)

    exit_code = 1 if plan["status"] == "unresolved" else 0
    _emit(sync_result_payload(plan, exit_code))
    return exit_code


def sync_result_payload(
    plan: dict[str, Any], exit_code: int, error: str | None = None
) -> dict[str, Any]:
    comp = plan.get("comparison") or {}
    outcome = plan.get("outcome") or {}
    return {
        "exit_code": exit_code,
        "status": plan.get("status"),
        "action": plan.get("action"),
        "ready": plan.get("ready"),
        "applied": outcome.get("applied", False),
        "outcome": outcome.get("type"),
        "composer": comp.get("composer"),
        "build": comp.get("build"),
        "error": error,
        "config_path": display_path(plan.get("opencode", {}).get("config_path")),
        "opencode_catalog_size": len(plan.get("opencode", {}).get("model_ids", [])),
    }


if __name__ == "__main__":
    sys.exit(main())