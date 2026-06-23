#!/usr/bin/env python3
"""Bilingual strings (zh/en) for opencode-grok-composer-setup."""

from __future__ import annotations

import argparse
import locale
import os
import re
import sys
from typing import Any, TextIO

SUPPORTED = ("zh", "en")

_LANG_OVERRIDE_PATTERNS: list[tuple[str, str]] = [
    (r"(切换|改用|使用|显示|展示|汇报|报告|回复).{0,8}(中文|汉语|简体|繁体)", "zh"),
    (r"(switch|use|display|show|reply|report).{0,12}(chinese|中文)", "zh"),
    (r"^中文$|^用中文|^要中文", "zh"),
    (r"(切换|改用|使用|显示|展示|汇报|报告|回复|用|以).{0,6}(英文|英语)", "en"),
    (r"(switch|use|display|show|reply|report).{0,12}(english|英文)", "en"),
    (r"^english$|^用英文|^要英文|^以英文|^in english\b", "en"),
    (r"英文(展示|显示|回复|汇报|说明)", "en"),
]


def ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def detect_system_lang() -> str:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        val = os.environ.get(var, "").lower()
        if val.startswith("zh"):
            return "zh"
        if val.startswith("en"):
            return "en"
    try:
        loc = locale.getdefaultlocale()[0] or ""
        if loc.lower().startswith("zh"):
            return "zh"
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes

            lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            if lid in (0x0804, 0x0404, 0x0C04, 0x1004, 0x1404):
                return "zh"
        except Exception:
            pass
    return "en"


def parse_explicit_lang_override(user_text: str | None) -> str | None:
    if not user_text or not user_text.strip():
        return None
    text = user_text.strip()
    for pattern, lang in _LANG_OVERRIDE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return lang
    return None


def add_lang_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--lang", choices=["auto", *SUPPORTED], default="auto")
    parser.add_argument("--user-message", default=None)


def resolve_lang(arg_lang: str, user_text: str | None = None) -> str:
    if arg_lang in SUPPORTED:
        return arg_lang
    override = parse_explicit_lang_override(user_text)
    if override:
        return override
    return detect_system_lang()


MESSAGES: dict[str, dict[str, str]] = {
    "none": {"zh": "(无)", "en": "(none)"},
    "unset": {"zh": "(未设置)", "en": "(not set)"},
    "unknown": {"zh": "未知", "en": "unknown"},
    "result_prefix": {"zh": "结果:", "en": "Result:"},
    # table
    "tbl.title": {"zh": "Grok → OpenCode", "en": "Grok → OpenCode"},
    "tbl.summary_ok": {"zh": "全部就绪", "en": "All ready"},
    "tbl.summary_pending": {"zh": "尚有待办", "en": "Pending items"},
    "tbl.summary_error": {"zh": "运行出错", "en": "Run error"},
    "tbl.item": {"zh": "检查项", "en": "Check"},
    "tbl.status_col": {"zh": "状态", "en": "Status"},
    "tbl.before": {"zh": "之前", "en": "Before"},
    "tbl.after": {"zh": "之后", "en": "After"},
    "tbl.issues": {"zh": "问题与方案", "en": "Issues & fixes"},
    "tbl.grok_cli": {"zh": "Grok CLI", "en": "Grok CLI"},
    "tbl.grok_path": {"zh": "Grok PATH", "en": "Grok PATH"},
    "tbl.grok_oauth": {"zh": "Grok OAuth", "en": "Grok OAuth"},
    "tbl.grok_composer": {"zh": "Composer 默认 (Grok)", "en": "Composer default (Grok)"},
    "tbl.opencode_cli": {"zh": "OpenCode CLI", "en": "OpenCode CLI"},
    "tbl.opencode_oauth": {"zh": "OpenCode OAuth", "en": "OpenCode OAuth"},
    "tbl.oc_composer": {"zh": "OpenCode Composer", "en": "OpenCode Composer"},
    "tbl.oc_build": {"zh": "OpenCode Build", "en": "OpenCode Build"},
    # issues
    "issue.grok_missing": {"zh": "未安装 Grok Build CLI", "en": "Grok Build CLI not installed"},
    "issue.grok_not_in_path": {"zh": "Grok CLI 未加入 PATH", "en": "Grok CLI not on PATH"},
    "issue.grok_auth_missing": {
        "zh": "Grok 未完成 OAuth 授权",
        "en": "Grok OAuth not configured",
    },
    "issue.grok_auth_expired": {"zh": "Grok OAuth 已过期", "en": "Grok OAuth expired"},
    "issue.composer_missing": {
        "zh": "未找到模型 {composer}",
        "en": "Model {composer} not found",
    },
    "issue.composer_not_default": {
        "zh": "默认模型应为 {composer}（当前 {current}）",
        "en": "Default should be {composer} (now {current})",
    },
    "issue.opencode_missing": {"zh": "未安装 OpenCode CLI", "en": "OpenCode CLI not installed"},
    "issue.opencode_auth_missing": {
        "zh": "OpenCode 未配置 xAI OAuth",
        "en": "OpenCode missing xAI OAuth",
    },
    "issue.oc_composer_missing": {
        "zh": "OpenCode 未注册 Composer 模型",
        "en": "OpenCode Composer model not registered",
    },
    "issue.oc_build_missing": {
        "zh": "OpenCode 未注册 Build 模型",
        "en": "OpenCode Build model not registered",
    },
    # reasons
    "reason.grok_missing": {
        "zh": "全流程已执行，但 Grok CLI 安装步骤未成功",
        "en": "Pipeline ran but Grok CLI install did not succeed",
    },
    "reason.grok_not_in_path": {
        "zh": "Grok 已安装但终端找不到 grok 命令",
        "en": "Grok installed but grok command not found on PATH",
    },
    "reason.grok_auth_missing": {
        "zh": "已自动运行 grok login，但浏览器授权尚未完成或已超时",
        "en": "grok login ran but browser auth not completed or timed out",
    },
    "reason.grok_auth_expired": {
        "zh": "Grok OAuth 凭证已过期",
        "en": "Grok OAuth credentials expired",
    },
    "reason.composer_missing": {
        "zh": "Grok 模型缓存中无 {composer}",
        "en": "{composer} not in Grok model cache",
    },
    "reason.composer_not_default": {
        "zh": "Grok config.toml 默认模型不是 {composer}",
        "en": "Grok config.toml default is not {composer}",
    },
    "reason.opencode_missing": {
        "zh": "未检测到 OpenCode CLI，无法写入模型配置",
        "en": "OpenCode CLI not found; cannot write model config",
    },
    "reason.opencode_auth_missing": {
        "zh": "Grok 已授权但 OpenCode 侧 OAuth 未迁移成功",
        "en": "Grok authed but OpenCode OAuth migration did not complete",
    },
    "reason.oc_composer_missing.no_opencode": {
        "zh": "OpenCode 未安装，模型同步步骤无法写入配置",
        "en": "OpenCode not installed; model sync cannot write config",
    },
    "reason.oc_composer_missing.not_run": {
        "zh": "模型同步步骤未执行（前序步骤失败或流程中断）",
        "en": "Model sync step did not run (earlier step failed)",
    },
    "reason.oc_composer_missing.unresolved": {
        "zh": "模型同步未成功写入 {grok_id} 到 opencode.json（{detail}）",
        "en": "Model sync did not write {grok_id} to opencode.json ({detail})",
    },
    "reason.oc_composer_missing.sync_error": {
        "zh": "模型同步报错: {error}",
        "en": "Model sync error: {error}",
    },
    "reason.oc_composer_missing.sync_failed": {
        "zh": "discover-xai-models.py 失败（退出码 {code}）: {detail}",
        "en": "discover-xai-models.py failed (exit {code}): {detail}",
    },
    "reason.oc_composer_missing.write_mismatch": {
        "zh": "同步脚本声称已写入，但 {path} 中仍无 Composer 条目，请检查文件权限或路径",
        "en": "Sync reported write but no Composer entry in {path}; check permissions",
    },
    "reason.oc_composer_missing.still_missing": {
        "zh": "同步已执行但未在 opencode.json 的 provider.xai.models 中找到 Composer",
        "en": "Sync ran but no Composer in provider.xai.models",
    },
    "reason.oc_build_missing.no_opencode": {
        "zh": "OpenCode 未安装，模型同步步骤无法写入配置",
        "en": "OpenCode not installed; model sync cannot write config",
    },
    "reason.oc_build_missing.not_run": {
        "zh": "模型同步步骤未执行（前序步骤失败或流程中断）",
        "en": "Model sync step did not run (earlier step failed)",
    },
    "reason.oc_build_missing.unresolved": {
        "zh": "模型同步未成功写入 {grok_id} 到 opencode.json（{detail}）",
        "en": "Model sync did not write {grok_id} to opencode.json ({detail})",
    },
    "reason.oc_build_missing.sync_error": {
        "zh": "模型同步报错: {error}",
        "en": "Model sync error: {error}",
    },
    "reason.oc_build_missing.sync_failed": {
        "zh": "discover-xai-models.py 失败（退出码 {code}）: {detail}",
        "en": "discover-xai-models.py failed (exit {code}): {detail}",
    },
    "reason.oc_build_missing.write_mismatch": {
        "zh": "同步脚本声称已写入，但 {path} 中仍无 Build 条目",
        "en": "Sync reported write but no Build entry in {path}",
    },
    "reason.oc_build_missing.still_missing": {
        "zh": "同步已执行但未在 opencode.json 中找到 grok-build* 模型",
        "en": "Sync ran but no grok-build* in opencode.json",
    },
    "reason.action_failed": {
        "zh": "步骤 {action} 运行失败: {detail}",
        "en": "Step {action} failed: {detail}",
    },
    "reason.action_failed_detail": {
        "zh": "步骤 {action}: {detail}",
        "en": "Step {action}: {detail}",
    },
    # fixes
    "fix.grok_missing": {
        "zh": "1. 检查网络后重新运行 /opencode-grok-composer-setup（会自动安装）\n2. 若仍失败，手动安装: curl -fsSL https://x.ai/cli/install.sh | bash\n3. 确认 ~/.grok/bin/grok 存在",
        "en": "1. Re-run /opencode-grok-composer-setup (auto-installs)\n2. If still fails: curl -fsSL https://x.ai/cli/install.sh | bash\n3. Confirm ~/.grok/bin/grok exists",
    },
    "fix.grok_not_in_path": {
        "zh": "1. 重新运行 /opencode-grok-composer-setup（会自动写入 PATH）\n2. 或手动将 ~/.grok/bin 加入 ~/.zshrc / ~/.bashrc 的 PATH\n3. 重开终端后执行 which grok",
        "en": "1. Re-run /opencode-grok-composer-setup (auto-fixes PATH)\n2. Or add ~/.grok/bin to PATH in ~/.zshrc\n3. Reopen terminal; run which grok",
    },
    "fix.grok_auth_missing": {
        "zh": "1. 在终端执行 grok login --oauth（或 --device-auth）\n2. 浏览器完成 SuperGrok 授权\n3. 重新运行 /opencode-grok-composer-setup（会自动配置 Composer 并同步 OpenCode）",
        "en": "1. Run grok login --oauth (or --device-auth)\n2. Complete SuperGrok auth in browser\n3. Re-run /opencode-grok-composer-setup (auto config + sync)",
    },
    "fix.grok_auth_expired": {
        "zh": "1. 终端执行 grok login 重新授权\n2. 重新运行 /opencode-grok-composer-setup",
        "en": "1. Run grok login\n2. Re-run /opencode-grok-composer-setup",
    },
    "fix.composer_missing": {
        "zh": "1. 终端执行 grok models，确认含 grok-composer-2.5-fast\n2. 若无，检查 Grok 订阅与网络\n3. 重新运行 /opencode-grok-composer-setup",
        "en": "1. Run grok models; confirm grok-composer-2.5-fast\n2. Check subscription/network\n3. Re-run /opencode-grok-composer-setup",
    },
    "fix.composer_not_default": {
        "zh": "1. 重新运行 /opencode-grok-composer-setup（会自动写 config.toml）\n2. 或手动编辑 ~/.grok/config.toml 设置 default = \"grok-composer-2.5-fast\"",
        "en": "1. Re-run /opencode-grok-composer-setup (writes config.toml)\n2. Or edit ~/.grok/config.toml default",
    },
    "fix.opencode_missing": {
        "zh": "1. 按 https://opencode.ai/docs/ 安装 OpenCode CLI\n2. 终端确认 opencode --version 可用\n3. 重新运行 /opencode-grok-composer-setup",
        "en": "1. Install OpenCode from https://opencode.ai/docs/\n2. Confirm opencode --version works\n3. Re-run /opencode-grok-composer-setup",
    },
    "fix.opencode_auth_missing": {
        "zh": "1. 先确保 Grok 已完成 grok login\n2. 重新运行 /opencode-grok-composer-setup（会自动执行 OAuth 迁移）\n3. 检查 ~/.local/share/opencode/auth.json 含 xAI OAuth",
        "en": "1. Ensure grok login completed\n2. Re-run /opencode-grok-composer-setup (auto OAuth migrate)\n3. Check ~/.local/share/opencode/auth.json",
    },
    "fix.oc_composer_missing.no_opencode": {
        "zh": "1. 安装 OpenCode CLI\n2. 重新运行 /opencode-grok-composer-setup",
        "en": "1. Install OpenCode CLI\n2. Re-run /opencode-grok-composer-setup",
    },
    "fix.oc_composer_missing.unresolved": {
        "zh": "1. 确认 Grok 已 grok login 且 OpenCode 已安装\n2. 检查 ~/.config/opencode/opencode.json 是否可写\n3. 重新运行 /opencode-grok-composer-setup（会将 grok-composer-2.5-fast 写入 provider.xai.models，配合 OAuth 使用）",
        "en": "1. Ensure grok login + OpenCode installed\n2. Check ~/.config/opencode/opencode.json is writable\n3. Re-run /opencode-grok-composer-setup (writes grok-composer-2.5-fast to provider.xai.models with OAuth)",
    },
    "fix.oc_composer_missing.retry": {
        "zh": "1. 重新运行 /opencode-grok-composer-setup\n2. 检查 ~/.config/opencode/opencode.json 的 provider.xai.models\n3. 确认 ~/.local/share/opencode/auth.json 含 xAI OAuth",
        "en": "1. Re-run /opencode-grok-composer-setup\n2. Check provider.xai.models in opencode.json\n3. Confirm xAI OAuth in auth.json",
    },
    "fix.oc_build_missing.no_opencode": {
        "zh": "1. 安装 OpenCode CLI\n2. 重新运行 /opencode-grok-composer-setup",
        "en": "1. Install OpenCode CLI\n2. Re-run /opencode-grok-composer-setup",
    },
    "fix.oc_build_missing.unresolved": {
        "zh": "1. 确认 Grok 已 grok login\n2. 重新运行 /opencode-grok-composer-setup（会将 grok-build* 写入 provider.xai.models）\n3. 检查 opencode.json 中 provider.xai.models 是否含 grok-build 条目",
        "en": "1. Ensure grok login\n2. Re-run /opencode-grok-composer-setup (writes grok-build* to provider.xai.models)\n3. Check provider.x.ai.models in opencode.json",
    },
    "fix.oc_build_missing.retry": {
        "zh": "1. 重新运行 /opencode-grok-composer-setup\n2. 检查 opencode.json 与 OAuth 配置",
        "en": "1. Re-run /opencode-grok-composer-setup\n2. Check opencode.json and OAuth",
    },
    "fix.action_failed": {
        "zh": "1. 查看上方终端完整错误输出\n2. 按原因修复后重新运行 /opencode-grok-composer-setup\n3. 涉及步骤: {action}",
        "en": "1. Read full terminal error above\n2. Fix cause and re-run /opencode-grok-composer-setup\n3. Step: {action}",
    },
    "issue.auto.grok_missing": {
        "zh": "自动安装 Grok CLI 并修复 PATH",
        "en": "Auto-install Grok CLI and fix PATH",
    },
    "issue.manual.grok_missing": {
        "zh": "手动: irm https://x.ai/cli/install.ps1 | iex（Win）或 install.sh（Unix）",
        "en": "Manual: irm install.ps1 (Win) or install.sh (Unix)",
    },
    "issue.auto.grok_not_in_path": {
        "zh": "自动写入 ~/.grok/bin 到 PATH",
        "en": "Auto-add ~/.grok/bin to PATH",
    },
    "issue.manual.grok_not_in_path": {
        "zh": "手动将 ~/.grok/bin 加入 PATH",
        "en": "Manually add ~/.grok/bin to PATH",
    },
    "issue.auto.grok_auth_missing": {
        "zh": "自动运行 grok login，请在浏览器确认",
        "en": "Auto-run grok login; confirm in browser",
    },
    "issue.manual.grok_auth_missing": {
        "zh": "手动: grok login --oauth 或 --device-auth",
        "en": "Manual: grok login --oauth or --device-auth",
    },
    "issue.auto.grok_auth_expired": {
        "zh": "自动重新 grok login",
        "en": "Auto re-run grok login",
    },
    "issue.manual.grok_auth_expired": {
        "zh": "手动: grok login",
        "en": "Manual: grok login",
    },
    "issue.auto.composer_missing": {
        "zh": "自动写入 Composer 默认模型并同步 OpenCode",
        "en": "Auto-set Composer default and sync OpenCode",
    },
    "issue.manual.composer_missing": {
        "zh": "手动: grok models 确认含 grok-composer-2.5-fast",
        "en": "Manual: grok models — confirm grok-composer-2.5-fast",
    },
    "issue.auto.composer_not_default": {
        "zh": "自动写入 ~/.grok/config.toml",
        "en": "Auto-write ~/.grok/config.toml",
    },
    "issue.manual.composer_not_default": {
        "zh": "手动编辑 config.toml [models] default",
        "en": "Manually edit config.toml [models] default",
    },
    "issue.auto.opencode_missing": {
        "zh": "需先安装 OpenCode",
        "en": "Install OpenCode first",
    },
    "issue.manual.opencode_missing": {
        "zh": "手动: https://opencode.ai/docs/",
        "en": "Manual: https://opencode.ai/docs/",
    },
    "issue.auto.opencode_auth_missing": {
        "zh": "Grok 授权后自动迁移 OAuth 到 OpenCode",
        "en": "Auto-migrate OAuth after Grok auth",
    },
    "issue.manual.opencode_auth_missing": {
        "zh": "先完成 Grok 授权",
        "en": "Complete Grok auth first",
    },
    "issue.after.grok_auth_missing": {
        "zh": "确认后自动设置 Composer 并同步 OpenCode",
        "en": "Then auto-set Composer and sync OpenCode",
    },
    "issue.after.grok_auth_expired": {
        "zh": "重新授权后自动同步 OpenCode",
        "en": "Then auto-sync OpenCode",
    },
    "issue.after.opencode_auth_missing": {
        "zh": "Grok 授权后自动迁移",
        "en": "Auto-migrate after Grok auth",
    },
    "issue.action_failed": {
        "zh": "{action} 失败: {detail}",
        "en": "{action} failed: {detail}",
    },
    "issue.auto.action_failed": {
        "zh": "查看终端错误输出后重试",
        "en": "Check terminal output and retry",
    },
    "issue.manual.action_failed": {
        "zh": "按错误信息手动修复后重试",
        "en": "Fix manually from error, then retry",
    },
    # setup (internal)
    "setup.grok_exists": {"zh": "Grok CLI 已存在", "en": "Grok CLI present"},
    "setup.grok_install_fail": {"zh": "Grok 安装失败", "en": "Grok install failed"},
    "setup.grok_install_ok": {"zh": "Grok 安装完成", "en": "Grok installed"},
    "setup.path_skip_no_bin": {"zh": "跳过 PATH", "en": "Skip PATH"},
    "setup.path_skip_ok": {"zh": "PATH 已就绪", "en": "PATH OK"},
    "setup.path_ok": {"zh": "PATH 已更新", "en": "PATH updated"},
    "setup.models_ok": {"zh": "模型已配置", "en": "Models configured"},
    "setup.login_no_cli": {"zh": "无 Grok CLI", "en": "No Grok CLI"},
    "setup.login_skip": {"zh": "OAuth 已存在", "en": "OAuth present"},
    "setup.login_ok": {"zh": "OAuth 完成", "en": "OAuth done"},
    "setup.login_pending": {"zh": "OAuth 待浏览器确认", "en": "OAuth awaiting browser"},
    "setup.sync_fail_grok": {"zh": "Grok 未就绪", "en": "Grok not ready"},
    "setup.sync_oauth_skip": {"zh": "跳过 OAuth 迁移", "en": "Skip OAuth migrate"},
    "setup.sync_ok": {"zh": "同步完成", "en": "Sync done"},
    "setup.sync_partial": {"zh": "同步部分失败", "en": "Sync partial fail"},
    "setup.sync_unresolved": {"zh": "模型映射未解析", "en": "Model mapping unresolved"},
    "setup.done": {"zh": "完成", "en": "done"},
    "setup.fail": {"zh": "失败", "en": "failed"},
    # discover (subprocess)
    "ui.done_ok": {"zh": "✓ {summary}", "en": "✓ {summary}"},
    "ui.done_fail": {"zh": "✗ {summary}", "en": "✗ {summary}"},
    "sync.failed_intro": {"zh": "同步失败:", "en": "Sync failed:"},
    "sync.unresolved": {"zh": "模型未解析", "en": "model unresolved"},
    "sync.failed_tip": {
        "zh": "确认 Grok 已登录，重新运行 /opencode-grok-composer-setup 写入 opencode.json",
        "en": "Ensure grok login, re-run /opencode-grok-composer-setup to write opencode.json",
    },
    "outcome.failed": {"zh": "同步失败", "en": "Sync failed"},
    "outcome.no_change": {"zh": "无需更新", "en": "No change"},
    "outcome.configured": {"zh": "首次配置", "en": "First config"},
    "outcome.updated": {"zh": "已更新", "en": "Updated"},
    "compare.title": {"zh": "配置对比", "en": "Comparison"},
    "compare.status.synced": {"zh": "已同步", "en": "synced"},
    "compare.status.outdated": {"zh": "待更新", "en": "outdated"},
    "compare.status.not_configured": {"zh": "未配置", "en": "not configured"},
    "compare.status.unresolved": {"zh": "未解析", "en": "unresolved"},
    "compare.map.ok": {"zh": "一致", "en": "ok"},
    "compare.map.missing": {"zh": "缺失", "en": "missing"},
    "compare.map.unresolved": {"zh": "未解析", "en": "unresolved"},
}


class I18n:
    def __init__(self, lang: str) -> None:
        self.lang = lang if lang in SUPPORTED else "en"

    def t(self, key: str, **kwargs: Any) -> str:
        entry = MESSAGES.get(key, {})
        text = entry.get(self.lang) or entry.get("en") or key
        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError:
                return text
        return text


def issue_message(i18n: I18n, issue_id: str, **kwargs: Any) -> str:
    return i18n.t(f"issue.{issue_id}", **kwargs)


def issue_auto_hint(i18n: I18n, issue_id: str, **kwargs: Any) -> str:
    return i18n.t(f"issue.auto.{issue_id}", **kwargs)


def issue_manual_hint(i18n: I18n, issue_id: str, **kwargs: Any) -> str:
    return i18n.t(f"issue.manual.{issue_id}", **kwargs)


def issue_after_hint(i18n: I18n, issue_id: str, **kwargs: Any) -> str | None:
    key = f"issue.after.{issue_id}"
    entry = MESSAGES.get(key)
    if not entry:
        return None
    return i18n.t(key, **kwargs)