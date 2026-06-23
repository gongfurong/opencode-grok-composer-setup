#!/usr/bin/env python3
"""Install, configure, authorize Grok Build CLI and sync Composer to OpenCode."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from i18n import (
    I18n,
    MESSAGES,
    add_lang_argument,
    ensure_utf8_stdio,
    issue_after_hint,
    issue_auto_hint,
    issue_manual_hint,
    issue_message,
    resolve_lang,
)

TARGET_COMPOSER = "grok-composer-2.5-fast"
TARGET_BUILD = "grok-build"
GROK_AUTH_PREFIX = "https://auth.x.ai::"
CURRENT_I18N: I18n | None = None
SCRIPT_DIR = Path(__file__).resolve().parent

ROW_KEYS = (
    "grok_cli",
    "grok_path",
    "grok_oauth",
    "grok_composer",
    "opencode_cli",
    "opencode_oauth",
    "oc_composer",
    "oc_build",
)

LOGIN_TIMEOUT = 600

ISSUE_MODES: dict[str, str] = {
    "grok_missing": "auto",
    "grok_not_in_path": "auto",
    "grok_auth_missing": "semi",
    "grok_auth_expired": "semi",
    "composer_missing": "auto",
    "composer_not_default": "auto",
    "opencode_missing": "manual",
    "opencode_auth_missing": "auto",
    "oc_composer_missing": "auto",
    "oc_build_missing": "auto",
    "action_failed": "semi",
}

PIPELINE = (
    "install-grok",
    "fix-path",
    "grok-login",
    "configure-models",
    "sync-opencode",
)


def home() -> Path:
    return Path(os.path.expanduser("~"))


def grok_dir() -> Path:
    return home() / ".grok"


def grok_bin_dir() -> Path:
    return grok_dir() / "bin"


def display_path(path: str | Path | None) -> str | None:
    if not path:
        return None
    text = str(path)
    home_str = str(home())
    if text.startswith(home_str):
        return "~" + text[len(home_str) :].replace("\\", "/")
    return text.replace("\\", "/")


def detect_platform() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "macos"
    return "linux"


def run_command(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return 127, "", "command not found"
    except subprocess.TimeoutExpired:
        return 124, "", "command timed out"


def run_shell(command: str, shell: bool = True) -> tuple[int, str]:
    result = subprocess.run(
        command,
        shell=shell,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.strip()


def find_grok_binary() -> Path | None:
    which = shutil.which("grok")
    if which:
        return Path(which)
    bin_dir = grok_bin_dir()
    for name in ("grok.exe", "grok"):
        candidate = bin_dir / name
        if candidate.is_file():
            return candidate
    return None


def grok_installed() -> bool:
    return find_grok_binary() is not None


def grok_in_path() -> bool:
    return shutil.which("grok") is not None


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as f:
        return json.load(f)


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
            field = "fork_secondary_model" if key == "secondary" else "default"
            pattern = rf"\[{section}\][^\[]*?{field}\s*=\s*\"([^\"]+)\""
            match = re.search(pattern, text, re.DOTALL)
            if match:
                out[key] = match.group(1)
        return out


def load_grok_model_ids() -> list[str]:
    cache_path = grok_dir() / "models_cache.json"
    if cache_path.is_file():
        return list(load_json(cache_path).get("models", {}).keys())
    binary = find_grok_binary()
    if not binary:
        return []
    code, stdout, _ = run_command([str(binary), "models"])
    if code != 0:
        return []
    ids: list[str] = []
    for line in stdout.splitlines():
        match = re.match(r"^[*-]\s+(\S+)", line.strip())
        if match:
            ids.append(match.group(1))
    return ids


def check_grok_auth() -> dict[str, Any]:
    auth_path = grok_dir() / "auth.json"
    if not auth_path.is_file():
        return {"present": False, "oauth": False, "expired": None, "path": display_path(auth_path)}
    auth = load_json(auth_path)
    entry = None
    for key, value in auth.items():
        if key.startswith(GROK_AUTH_PREFIX) and isinstance(value, dict):
            entry = value
            break
    if not entry:
        return {"present": True, "oauth": False, "expired": None, "path": display_path(auth_path)}
    expires_at = entry.get("expires_at")
    expired = False
    if isinstance(expires_at, str):
        try:
            dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            expired = dt <= datetime.now(timezone.utc)
        except ValueError:
            expired = None
    complete = bool(entry.get("key") and entry.get("refresh_token") and expires_at)
    return {
        "present": True,
        "oauth": complete,
        "expired": expired,
        "path": display_path(auth_path),
    }


def opencode_xai_model_flags() -> dict[str, bool]:
    path = home() / ".config" / "opencode" / "opencode.json"
    if not path.is_file():
        return {"composer": False, "build": False}
    cfg = load_json(path)
    ids = list(cfg.get("provider", {}).get("xai", {}).get("models", {}).keys())
    return {
        "composer": any("composer" in m for m in ids),
        "build": any(m.startswith("grok-build") for m in ids),
    }


def check_opencode() -> dict[str, Any]:
    code, stdout, _ = run_command(["opencode", "--version"])
    installed = code == 0
    version = stdout.splitlines()[0] if stdout else None
    auth_path = home() / ".local" / "share" / "opencode" / "auth.json"
    xai_oauth = False
    if auth_path.is_file():
        auth = load_json(auth_path)
        xai = auth.get("xai", {})
        xai_oauth = isinstance(xai, dict) and xai.get("type") == "oauth" and bool(xai.get("access"))
    flags = opencode_xai_model_flags()
    return {
        "installed": installed,
        "version": version,
        "xai_oauth": xai_oauth,
        "auth_path": display_path(auth_path),
        "xai_composer": flags["composer"],
        "xai_build": flags["build"],
    }


def composer_default_ok(default_model: str | None, model_ids: list[str]) -> bool:
    if not default_model:
        return False
    if default_model == TARGET_COMPOSER:
        return True
    if "composer" in default_model and "2.5" in default_model and "fast" in default_model:
        return default_model in model_ids
    return False


def build_check() -> dict[str, Any]:
    binary = find_grok_binary()
    installed = binary is not None
    version = None
    if installed:
        code, stdout, _ = run_command([str(binary), "--version"])
        if code == 0:
            version = stdout.splitlines()[0] if stdout else stdout
    config_path = grok_dir() / "config.toml"
    config = parse_grok_config(config_path)
    model_ids = load_grok_model_ids() if installed else []
    auth = check_grok_auth() if installed else {
        "present": False,
        "oauth": False,
        "expired": None,
        "path": display_path(grok_dir() / "auth.json"),
    }
    return {
        "grok_cli": {
            "installed": installed,
            "in_path": grok_in_path(),
            "binary": display_path(binary) if binary else None,
            "version": version,
        },
        "grok_auth": auth,
        "grok_models": {
            "composer_25_fast_available": TARGET_COMPOSER in model_ids,
            "default_model": config.get("default"),
            "default_ok": composer_default_ok(config.get("default"), model_ids),
        },
    }


def collect_issues(state: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    cli = state["grok_cli"]
    auth = state["grok_auth"]
    models = state["grok_models"]
    opencode = state["opencode"]

    def add(issue_id: str, severity: str, **context: Any) -> None:
        issues.append({"id": issue_id, "severity": severity, "context": context})

    if not cli["installed"]:
        add("grok_missing", "error")
    elif not cli["in_path"]:
        add("grok_not_in_path", "warn")
    if cli["installed"] and not auth["oauth"]:
        add("grok_auth_missing", "error")
    elif auth.get("expired"):
        add("grok_auth_expired", "error")
    if cli["installed"] and not models["composer_25_fast_available"]:
        add("composer_missing", "error", composer=TARGET_COMPOSER)
    if cli["installed"] and models["composer_25_fast_available"] and not models["default_ok"]:
        add(
            "composer_not_default",
            "warn",
            composer=TARGET_COMPOSER,
            current=models.get("default_model") or "unset",
        )
    if not opencode["installed"]:
        add("opencode_missing", "warn")
    else:
        if not opencode["xai_oauth"]:
            add("opencode_auth_missing", "warn")
        if not opencode["xai_composer"]:
            add("oc_composer_missing", "warn")
        if not opencode["xai_build"]:
            add("oc_build_missing", "warn")
    return issues


def issue_mode(issue_id: str, state: dict[str, Any]) -> str:
    if issue_id == "opencode_auth_missing":
        auth = state.get("grok_auth", {})
        oauth_ok = bool(auth.get("oauth")) and auth.get("expired") is not True
        return "auto" if oauth_ok else "semi"
    return ISSUE_MODES.get(issue_id, "manual")


def localize_issues(
    i18n: I18n, issues: list[dict[str, Any]], state: dict[str, Any]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in issues:
        ctx = dict(item.get("context") or {})
        if ctx.get("current") == "unset":
            ctx["current"] = i18n.t("unset")
        issue_id = item["id"]
        mode = issue_mode(issue_id, state)
        after = issue_after_hint(i18n, issue_id, **ctx)
        out.append(
            {
                **item,
                "message": issue_message(i18n, issue_id, **ctx),
                "mode": mode,
                "action": issue_auto_hint(i18n, issue_id, **ctx)
                if mode in ("auto", "semi")
                else issue_manual_hint(i18n, issue_id, **ctx),
                "manual": issue_manual_hint(i18n, issue_id, **ctx),
                "after": after,
            }
        )
    return out


def gather_state(i18n: I18n | None = None) -> dict[str, Any]:
    i18n = i18n or I18n("en")
    state: dict[str, Any] = {
        "platform": detect_platform(),
        **build_check(),
        "opencode": check_opencode(),
    }
    raw = collect_issues(state)
    state["issues"] = localize_issues(i18n, raw, state)
    state["status"] = (
        "needs_setup"
        if any(x["severity"] == "error" for x in raw)
        else ("needs_sync" if raw else "ready")
    )
    return state


def yn(ok: bool) -> str:
    return "OK" if ok else "NO"


def table_rows(state: dict[str, Any]) -> dict[str, str]:
    cli = state["grok_cli"]
    auth = state["grok_auth"]
    models = state["grok_models"]
    oc = state["opencode"]
    oauth_ok = bool(auth.get("oauth")) and auth.get("expired") is not True
    return {
        "grok_cli": yn(cli["installed"]),
        "grok_path": yn(cli["in_path"]) if cli["installed"] else "NO",
        "grok_oauth": yn(oauth_ok),
        "grok_composer": yn(models.get("default_ok")),
        "opencode_cli": yn(oc["installed"]),
        "opencode_oauth": yn(bool(oc.get("xai_oauth"))),
        "oc_composer": yn(bool(oc.get("xai_composer"))),
        "oc_build": yn(bool(oc.get("xai_build"))),
    }


def _glyph(value: str) -> str:
    return {"OK": "✓", "NO": "✗"}.get(value, "·")


def _rows_unchanged(before: dict[str, str], after: dict[str, str]) -> bool:
    return all(before.get(k) == after.get(k) for k in ROW_KEYS)


def _summary_key(ok: bool, hard_error: bool) -> str:
    if ok:
        return "tbl.summary_ok"
    if hard_error:
        return "tbl.summary_error"
    return "tbl.summary_pending"


def _header_icon(ok: bool, hard_error: bool) -> str:
    if ok:
        return "✓"
    if hard_error:
        return "✗"
    return "○"


def _box_lines(icon: str, title: str, summary: str) -> list[str]:
    head = f" {icon}  {title}"
    sub = f"    {summary}"
    width = max(len(head), len(sub)) + 2
    bar = "─" * width
    return [f"┌{bar}┐", f"│{head.ljust(width)}│", f"│{sub.ljust(width)}│", f"└{bar}┘"]


def _format_issue_lines(i18n: I18n, issues: list[dict[str, Any]], style: str) -> list[str]:
    lines: list[str] = []
    for idx, item in enumerate(issues, 1):
        problem = item.get("problem") or item.get("message", "")
        reason = item.get("reason", "")
        fix = item.get("fix", "")

        if style == "md":
            lines.append(f"**{idx}. {problem}**")
            if reason:
                lines.append(f"- 原因: {reason}")
            if fix:
                lines.append("- 方案:")
                for step in fix.split("\n"):
                    step = step.strip()
                    if step:
                        lines.append(f"  - {step}")
            continue

        lines.append(f"  {idx}. {problem}")
        if reason:
            lines.append(f"     原因: {reason}")
        if fix:
            lines.append("     方案:")
            for step in fix.split("\n"):
                step = step.strip()
                if step:
                    lines.append(f"       {step}")
    return lines


def format_report(
    before: dict[str, str],
    after: dict[str, str],
    i18n: I18n,
    *,
    ok: bool,
    hard_error: bool,
    issues: list[dict[str, Any]] | None = None,
    style: str = "ascii",
) -> str:
    labels = {k: i18n.t(f"tbl.{k}") for k in ROW_KEYS}
    if style == "md":
        return _md_report(before, after, labels, i18n, ok, hard_error, issues)
    return _ascii_report(before, after, labels, i18n, ok, hard_error, issues)


def _ascii_report(
    before: dict[str, str],
    after: dict[str, str],
    labels: dict[str, str],
    i18n: I18n,
    ok: bool,
    hard_error: bool,
    issues: list[dict[str, Any]] | None,
) -> str:
    icon = _header_icon(ok, hard_error)
    summary = i18n.t(_summary_key(ok, hard_error))
    lines = ["", *_box_lines(icon, i18n.t("tbl.title"), summary), ""]

    compact = ok and _rows_unchanged(before, after)
    col_item = 22
    if compact:
        lines.append(f"  {i18n.t('tbl.item'):<{col_item}}{i18n.t('tbl.status_col')}")
        lines.append(f"  {'─' * (col_item + 6)}")
        for key in ROW_KEYS:
            lines.append(
                f"  {labels[key]:<{col_item}}{_glyph(after.get(key, '·'))}"
            )
    else:
        lines.append(
            f"  {i18n.t('tbl.item'):<{col_item}}"
            f"{i18n.t('tbl.before'):^8}"
            f"{i18n.t('tbl.after'):^8}"
        )
        lines.append(f"  {'─' * (col_item + 18)}")
        for key in ROW_KEYS:
            b, a = before.get(key, "·"), after.get(key, "·")
            arrow = " → " if b != a else "   "
            lines.append(
                f"  {labels[key]:<{col_item}}"
                f"{_glyph(b):^8}{arrow}{_glyph(a):^5}"
            )

    if issues:
        lines.extend(["", f"── {i18n.t('tbl.issues')} {'─' * 20}"])
        lines.extend(_format_issue_lines(i18n, issues, "ascii"))
    lines.append("")
    return "\n".join(lines)


def _md_report(
    before: dict[str, str],
    after: dict[str, str],
    labels: dict[str, str],
    i18n: I18n,
    ok: bool,
    hard_error: bool,
    issues: list[dict[str, Any]] | None,
) -> str:
    icon = _header_icon(ok, hard_error)
    summary = i18n.t(_summary_key(ok, hard_error))
    lines = ["", f"### {icon} {i18n.t('tbl.title')}", "", f"**{summary}**", ""]

    if ok and _rows_unchanged(before, after):
        lines.extend([f"| {i18n.t('tbl.item')} | {i18n.t('tbl.status_col')} |", "| :--- | :---: |"])
        for key in ROW_KEYS:
            lines.append(f"| {labels[key]} | {_glyph(after.get(key, '·'))} |")
    else:
        lines.extend([
            f"| {i18n.t('tbl.item')} | {i18n.t('tbl.before')} | {i18n.t('tbl.after')} |",
            "| :--- | :---: | :---: |",
        ])
        for key in ROW_KEYS:
            lines.append(
                f"| {labels[key]} | {_glyph(before.get(key, '·'))} | "
                f"{_glyph(after.get(key, '·'))} |"
            )

    if issues:
        lines.extend(["", f"**{i18n.t('tbl.issues')}**", ""])
        lines.extend(_format_issue_lines(i18n, issues, "md"))
    lines.append("")
    return "\n".join(lines)


def _i18n() -> I18n:
    return CURRENT_I18N or I18n("en")


def install_grok() -> dict[str, Any]:
    i18n = _i18n()
    if grok_installed():
        binary = find_grok_binary()
        return {
            "action": "install-grok",
            "status": "skipped",
            "message": i18n.t("setup.grok_exists", path=display_path(binary)),
        }

    plat = detect_platform()
    if plat == "windows":
        cmd = "irm https://x.ai/cli/install.ps1 | iex"
    else:
        cmd = "curl -fsSL https://x.ai/cli/install.sh | bash"

    code, output = run_shell(cmd)
    if code != 0 and not grok_installed():
        return {
            "action": "install-grok",
            "status": "failed",
            "message": i18n.t("setup.grok_install_fail"),
            "output": output[-2000:],
        }

    binary = find_grok_binary()
    return {
        "action": "install-grok",
        "status": "ok",
        "message": i18n.t("setup.grok_install_ok", path=display_path(binary)),
        "output": output[-500:] if output else None,
    }


def _unix_shell_rc_files() -> list[Path]:
    files: list[Path] = []
    if detect_platform() == "macos":
        files.append(home() / ".zshrc")
    files.append(home() / ".bashrc")
    if detect_platform() == "linux":
        files.append(home() / ".profile")
    return files


def _append_unix_path(export_line: str) -> list[str]:
    updated: list[str] = []
    for rc_file in _unix_shell_rc_files():
        text = rc_file.read_text(encoding="utf-8") if rc_file.is_file() else ""
        if export_line in text:
            continue
        rc_file.parent.mkdir(parents=True, exist_ok=True)
        with rc_file.open("a", encoding="utf-8") as f:
            f.write(f"\n# Grok Build CLI\n{export_line}\n")
        updated.append(display_path(rc_file) or str(rc_file))
    return updated


def fix_path() -> dict[str, Any]:
    i18n = _i18n()
    bin_dir = grok_bin_dir()
    if not bin_dir.is_dir():
        return {
            "action": "fix-path",
            "status": "skipped",
            "message": i18n.t("setup.path_skip_no_bin"),
        }

    if shutil.which("grok"):
        return {
            "action": "fix-path",
            "status": "skipped",
            "message": i18n.t("setup.path_skip_ok"),
        }

    bin_str = str(bin_dir)
    plat = detect_platform()
    output = ""
    updated_files: list[str] = []

    if plat == "windows":
        ps = (
            f"$bin='{bin_str}';"
            "$cur=[Environment]::GetEnvironmentVariable('Path','User');"
            "if ($cur -split ';' | Where-Object { $_ -eq $bin }) { exit 0 };"
            "[Environment]::SetEnvironmentVariable('Path', $cur + ';' + $bin, 'User')"
        )
        code, output = run_shell(f'powershell -NoProfile -Command "{ps}"')
        if bin_str not in os.environ.get("Path", ""):
            os.environ["Path"] = os.environ.get("Path", "") + f";{bin_str}"
        status = "ok" if code == 0 or shutil.which("grok") else "failed"
    else:
        export_line = 'export PATH="$HOME/.grok/bin:$PATH"'
        updated_files = _append_unix_path(export_line)
        if bin_str not in os.environ.get("PATH", ""):
            os.environ["PATH"] = f"{bin_dir}:{os.environ.get('PATH', '')}"
        code = 0
        status = "ok" if shutil.which("grok") else "warn"

    message = i18n.t("setup.path_ok", path=display_path(bin_dir))
    if updated_files:
        message += f" ({', '.join(updated_files)})"

    return {
        "action": "fix-path",
        "status": status,
        "message": message,
        "output": output[-500:] if output else None,
        "updated_files": updated_files,
    }


def patch_toml_value(text: str, section: str, key: str, value: str) -> str:
    pattern = rf"(\[{re.escape(section)}\][^\[]*?{re.escape(key)}\s*=\s*)\"[^\"]*\""
    replacement = rf'\1"{value}"'
    if re.search(pattern, text, re.DOTALL):
        return re.sub(pattern, replacement, text, count=1, flags=re.DOTALL)

    block = f'\n[{section}]\n{key} = "{value}"\n'
    if f"[{section}]" in text:
        insert_at = text.index(f"[{section}]")
        next_section = re.search(r"\n\[", text[insert_at + len(section) + 2 :])
        if next_section:
            pos = insert_at + len(section) + 2 + next_section.start()
            return text[:pos] + f'{key} = "{value}"\n' + text[pos:]
        return text.rstrip() + f'\n{key} = "{value}"\n'
    return text.rstrip() + block


def configure_models() -> dict[str, Any]:
    config_path = grok_dir() / "config.toml"
    grok_dir().mkdir(parents=True, exist_ok=True)
    text = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""

    text = patch_toml_value(text, "models", "default", TARGET_COMPOSER)
    text = patch_toml_value(text, "ui", "fork_secondary_model", TARGET_BUILD)
    config_path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")

    i18n = _i18n()
    return {
        "action": "configure-models",
        "status": "ok",
        "message": i18n.t(
            "setup.models_ok", composer=TARGET_COMPOSER, build=TARGET_BUILD
        ),
        "config_path": display_path(config_path),
    }


def grok_auth_ready() -> bool:
    auth = check_grok_auth()
    return bool(auth.get("oauth")) and auth.get("expired") is not True


def _login_command(binary: Path) -> list[str]:
    cmd = [str(binary), "login"]
    if sys.stdin.isatty() and sys.stdout.isatty():
        cmd.append("--oauth")
    else:
        cmd.append("--device-auth")
    return cmd


def grok_login() -> dict[str, Any]:
    i18n = _i18n()
    binary = find_grok_binary()
    if not binary:
        return {
            "action": "grok-login",
            "status": "skipped",
            "message": i18n.t("setup.login_no_cli"),
        }

    if grok_auth_ready():
        return {
            "action": "grok-login",
            "status": "skipped",
            "message": i18n.t("setup.login_skip"),
        }

    cmd = _login_command(binary)
    try:
        subprocess.run(cmd, timeout=LOGIN_TIMEOUT, check=False)
    except subprocess.TimeoutExpired:
        pass

    if grok_auth_ready():
        return {
            "action": "grok-login",
            "status": "ok",
            "message": i18n.t("setup.login_ok"),
        }

    manual = "grok login --oauth" if "--oauth" in cmd else "grok login --device-auth"
    return {
        "action": "grok-login",
        "status": "pending",
        "message": i18n.t("setup.login_pending"),
        "command": manual,
    }


def run_python_script(name: str, extra_args: list[str] | None = None) -> dict[str, Any]:
    script = SCRIPT_DIR / name
    if not script.is_file():
        return {
            "action": name,
            "status": "failed",
            "message": f"脚本不存在: {script}",
        }

    i18n = _i18n()
    extra: list[str] = list(extra_args or [])
    if name == "discover-xai-models.py":
        extra = ["--lang", i18n.lang, "--emit-result"] + extra
    elif name == "migrate-grok-oauth.py":
        extra = ["--quiet"] + extra
    cmd = [sys.executable, str(script)] + extra
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    output = (result.stdout or "") + (result.stderr or "")
    sync_result: dict[str, Any] | None = None
    summary = ""
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("SYNC_RESULT:"):
            try:
                sync_result = json.loads(stripped[len("SYNC_RESULT:") :])
            except json.JSONDecodeError:
                pass
            continue
        if stripped.startswith("结果:") or stripped.startswith("Result:"):
            summary = stripped.split(":", 1)[1].strip()
    if not summary:
        for line in reversed(output.splitlines()):
            stripped = line.strip()
            if stripped.startswith("ERROR:"):
                summary = stripped[6:].strip()
                break
    if not summary and sync_result:
        status = sync_result.get("status")
        if status == "unresolved":
            parts = []
            for fam in ("composer", "build"):
                entry = sync_result.get(fam) or {}
                if entry.get("status") == "unresolved":
                    parts.append(
                        f"{entry.get('grok_id')}: {entry.get('reason', 'unresolved')}"
                    )
            summary = "; ".join(parts) if parts else i18n.t("setup.sync_unresolved")
        elif sync_result.get("error"):
            summary = str(sync_result["error"])[:200]
    if not summary and output.strip():
        for line in reversed(output.splitlines()):
            stripped = line.strip()
            if stripped and not stripped.startswith("SYNC_RESULT:"):
                summary = stripped[:200]
                break
    return {
        "action": name,
        "status": "ok" if result.returncode == 0 else "failed",
        "exit_code": result.returncode,
        "message": summary or (
            i18n.t("setup.done") if result.returncode == 0 else i18n.t("setup.fail")
        ),
        "output": output.strip()[-4000:],
        "sync_result": sync_result,
    }


def sync_opencode() -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    model_sync = run_python_script("discover-xai-models.py")
    results.append(model_sync)

    if not grok_installed():
        return {
            "action": "sync-opencode",
            "status": "failed",
            "message": _i18n().t("setup.sync_fail_grok"),
            "steps": results,
        }

    auth_path = grok_dir() / "auth.json"
    if auth_path.is_file():
        oauth_sync = run_python_script("migrate-grok-oauth.py")
        results.append(oauth_sync)
    else:
        results.append(
            {
                "action": "migrate-grok-oauth.py",
                "status": "skipped",
                "message": _i18n().t("setup.sync_oauth_skip"),
            }
        )

    failed = [r for r in results if r.get("status") == "failed"]
    return {
        "action": "sync-opencode",
        "status": "failed" if failed else "ok",
        "message": _i18n().t("setup.sync_ok")
        if not failed
        else _i18n().t("setup.sync_partial"),
        "steps": results,
    }


ACTION_HANDLERS = {
    "install-grok": install_grok,
    "fix-path": fix_path,
    "configure-models": configure_models,
    "grok-login": grok_login,
    "sync-opencode": sync_opencode,
}

SOFT_RESULT_STATUSES = frozenset({"ok", "skipped", "pending", "warn"})


def iter_action_results(results: list[dict[str, Any]]):
    for result in results:
        yield result
        for step in result.get("steps") or []:
            yield step


def is_hard_failure(result: dict[str, Any]) -> bool:
    if result.get("status") in SOFT_RESULT_STATUSES:
        return False
    action = str(result.get("action", ""))
    if action == "grok-login":
        return False
    return result.get("status") == "failed"


def collect_hard_failures(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in iter_action_results(results) if is_hard_failure(r)]


def _find_step(results: list[dict[str, Any]] | None, name: str) -> dict[str, Any] | None:
    for result in results or []:
        if result.get("action") == name:
            return result
        for step in result.get("steps") or []:
            if step.get("action") == name:
                return step
    return None


def _sync_step(results: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    return _find_step(results, "discover-xai-models.py")


def _oc_model_reason(
    i18n: I18n,
    family: str,
    state: dict[str, Any],
    results: list[dict[str, Any]] | None,
) -> tuple[str, str]:
    key = f"oc_{family}_missing"
    oc = state.get("opencode", {})
    if not oc.get("installed"):
        return i18n.t(f"reason.{key}.no_opencode"), i18n.t(f"fix.{key}.no_opencode")

    step = _sync_step(results)
    if not step:
        return i18n.t(f"reason.{key}.not_run"), i18n.t(f"fix.{key}.retry")

    sync = step.get("sync_result") or {}
    entry = sync.get(family) or {}
    grok_id = entry.get("grok_id") or (
        TARGET_COMPOSER if family == "composer" else TARGET_BUILD
    )

    if step.get("status") == "failed":
        if sync.get("error"):
            return (
                i18n.t(f"reason.{key}.sync_error", error=sync["error"]),
                i18n.t(f"fix.{key}.unresolved"),
            )
        if entry.get("status") == "unresolved":
            detail = entry.get("reason") or i18n.t("unknown")
            return (
                i18n.t(
                    f"reason.{key}.unresolved",
                    grok_id=grok_id,
                    detail=detail,
                    catalog=sync.get("opencode_catalog_size", 0),
                ),
                i18n.t(f"fix.{key}.unresolved"),
            )
        detail = step.get("message") or i18n.t("unknown")
        return (
            i18n.t(
                f"reason.{key}.sync_failed",
                code=step.get("exit_code", 1),
                detail=detail,
            ),
            i18n.t(f"fix.{key}.retry"),
        )

    if sync.get("applied"):
        path = sync.get("config_path") or display_path(
            home() / ".config" / "opencode" / "opencode.json"
        )
        return (
            i18n.t(f"reason.{key}.write_mismatch", path=path),
            i18n.t(f"fix.{key}.retry"),
        )

    return i18n.t(f"reason.{key}.still_missing"), i18n.t(f"fix.{key}.retry")


def _issue_reason_fix(
    i18n: I18n,
    issue_id: str,
    state: dict[str, Any],
    results: list[dict[str, Any]] | None,
    ctx: dict[str, Any],
) -> tuple[str, str]:
    if issue_id == "oc_composer_missing":
        return _oc_model_reason(i18n, "composer", state, results)
    if issue_id == "oc_build_missing":
        return _oc_model_reason(i18n, "build", state, results)

    if issue_id == "action_failed":
        action = ctx.get("action", "unknown")
        detail = ctx.get("detail", "")
        output = ""
        step = _find_step(results, action) if results else None
        if step:
            output = (step.get("output") or "")[-300:]
        reason = i18n.t("reason.action_failed", action=action, detail=detail)
        if output and "ERROR:" in output:
            for line in output.splitlines():
                if "ERROR:" in line:
                    reason = i18n.t(
                        "reason.action_failed_detail",
                        action=action,
                        detail=line.strip(),
                    )
                    break
        return reason, i18n.t("fix.action_failed", action=action)

    reason_key = f"reason.{issue_id}"
    fix_key = f"fix.{issue_id}"
    reason = i18n.t(reason_key, **ctx) if reason_key in MESSAGES else ""
    fix = i18n.t(fix_key, **ctx) if fix_key in MESSAGES else ""
    if not reason:
        reason = issue_auto_hint(i18n, issue_id, **ctx)
    if not fix:
        fix = issue_manual_hint(i18n, issue_id, **ctx)
    return reason, fix


def _enrich_issue(
    item: dict[str, Any],
    i18n: I18n,
    state: dict[str, Any],
    results: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    ctx = dict(item.get("context") or {})
    if ctx.get("current") == "unset":
        ctx["current"] = i18n.t("unset")
    issue_id = item["id"]
    reason, fix = _issue_reason_fix(i18n, issue_id, state, results, ctx)
    return {
        "id": issue_id,
        "severity": item.get("severity", "warn"),
        "problem": issue_message(i18n, issue_id, **ctx),
        "reason": reason,
        "fix": fix,
    }


def build_display_issues(
    i18n: I18n,
    state: dict[str, Any],
    results: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    display: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in state.get("issues") or []:
        issue_id = item.get("id")
        if not issue_id or issue_id in seen:
            continue
        display.append(_enrich_issue(item, i18n, state, results))
        seen.add(issue_id)

    for result in results or []:
        if not is_hard_failure(result):
            continue
        action = str(result.get("action", "unknown"))
        if action == "sync-opencode":
            if any(
                is_hard_failure(s)
                for s in (result.get("steps") or [])
                if s.get("action") != "sync-opencode"
            ):
                continue
        if action in seen:
            continue
        ctx = {
            "action": action,
            "detail": str(result.get("message") or i18n.t("unknown")),
        }
        display.append(
            _enrich_issue(
                {"id": "action_failed", "severity": "error", "context": ctx},
                i18n,
                state,
                results,
            )
        )
        seen.add(action)

    return display


def main() -> int:
    ensure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Setup Grok Build CLI and sync OpenCode")
    parser.add_argument("--table", choices=["ascii", "md"], default="ascii")
    add_lang_argument(parser)
    args = parser.parse_args()

    global CURRENT_I18N
    lang = resolve_lang(args.lang, user_text=args.user_message)
    CURRENT_I18N = I18n(lang)
    i18n = _i18n()

    before_state = gather_state(i18n)
    before_rows = table_rows(before_state)

    results: list[dict[str, Any]] = []
    for action_name in PIPELINE:
        handler = ACTION_HANDLERS[action_name]
        try:
            result = handler()
        except Exception as exc:
            result = {
                "action": action_name,
                "status": "failed",
                "message": str(exc),
            }
        results.append(result)

    after_state = gather_state(i18n)
    after_rows = table_rows(after_state)
    hard_failed = collect_hard_failures(results)
    ok = not hard_failed and after_state["status"] == "ready"
    issues = build_display_issues(i18n, after_state, results) if not ok else []

    print(
        format_report(
            before_rows,
            after_rows,
            i18n,
            ok=ok,
            hard_error=bool(hard_failed),
            issues=issues or None,
            style=args.table,
        )
    )

    return 1 if hard_failed else 0


if __name__ == "__main__":
    sys.exit(main())