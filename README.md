# opencode-grok-composer-setup

**[English](#english)** | **[中文](#中文)**

---

<a id="english"></a>

## English

Configure **OpenCode** to use **Grok Composer** (and Build) via **SuperGrok OAuth**.  
A Grok skill with a silent, cross-platform setup pipeline and a single result table at the end.

### Features

- Installs **Grok Build CLI** and fixes `PATH` when needed
- Runs **`grok login`** automatically (OAuth or device auth) and waits for browser confirmation
- Sets **Composer** as the Grok CLI default model
- Registers **Composer / Build** in `opencode.json` and migrates OAuth to OpenCode
- Does **not** change OpenCode’s top-level `model`
- Bilingual output (`zh` / `en`) with `--lang auto` (system locale + Windows UI language)

### Requirements

- Python **3.10+**
- [Grok Build CLI](https://x.ai/cli) (installed automatically if missing)
- SuperGrok subscription for OAuth
- [OpenCode CLI](https://opencode.ai/docs/) (optional for Grok-only setup; required for sync)

### Quick start

**As a Grok skill** — copy this repo into your skills folder, e.g.:

```text
~/.grok/skills/opencode-grok-composer-setup/
```

Then trigger: `/opencode-grok-composer-setup` or phrases like `opencode grok composer`.

**Run the script directly:**

```bash
python3 scripts/setup-grok-composer.py --lang auto
```

For chat-friendly Markdown table output:

```bash
python3 scripts/setup-grok-composer.py --lang auto --table md
```

### Pipeline

```text
install-grok → fix-path → grok-login → configure-models → sync-opencode
```

| Step | What it does |
|------|----------------|
| `install-grok` | Install Grok Build CLI if missing |
| `fix-path` | Add `~/.grok/bin` to PATH |
| `grok-login` | OAuth login; pending auth is not a hard failure |
| `configure-models` | Default model → `grok-composer-2.5-fast` |
| `sync-opencode` | Write models to `opencode.json` + OAuth migrate |

### CLI options

| Flag | Description |
|------|-------------|
| `--lang auto\|zh\|en` | Output language (default: `auto`) |
| `--table ascii\|md` | Result table format (default: `ascii`) |
| `--user-message TEXT` | Optional user message for language override |

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Done, or pending items listed in the table |
| `1` | Hard error (install / script failure) |

### Project layout

```text
opencode-grok-composer-setup/
├── SKILL.md                 # Grok skill instructions (English)
├── README.md                # This file (EN / 中文)
├── scripts/
│   ├── setup-grok-composer.py   # Main entry
│   ├── discover-xai-models.py   # Grok → OpenCode model sync
│   ├── migrate-grok-oauth.py    # OAuth credential migration
│   └── i18n.py                  # Bilingual strings
```

### License

MIT — see [LICENSE](LICENSE).

---

<a id="中文"></a>

## 中文

通过 **SuperGrok OAuth** 配置 **OpenCode** 使用 **Grok Composer**（及 Build）。  
跨平台 Grok Skill：流程静默执行，结束时输出一张结果表。

### 功能

- 按需安装 **Grok Build CLI** 并修复 `PATH`
- 自动执行 **`grok login`**（OAuth 或设备码），等待浏览器确认
- 将 **Composer** 设为 Grok CLI 默认模型
- 在 `opencode.json` 注册 **Composer / Build**，并迁移 OAuth 到 OpenCode
- **不修改** OpenCode 顶层 `model`
- 双语输出（`zh` / `en`），`--lang auto` 跟随系统语言（含 Windows 显示语言）

### 环境要求

- Python **3.10+**
- [Grok Build CLI](https://x.ai/cli)（缺失时自动安装）
- SuperGrok 订阅（OAuth）
- [OpenCode CLI](https://opencode.ai/docs/)（仅配 Grok 时可无；同步 OpenCode 时需要）

### 快速开始

**作为 Grok Skill** — 将本仓库放到 skills 目录，例如：

```text
~/.grok/skills/opencode-grok-composer-setup/
```

触发：`/opencode-grok-composer-setup` 或「配置 opencode grok composer」等说法。

**直接运行脚本：**

```bash
python3 scripts/setup-grok-composer.py --lang auto
```

对话里用 Markdown 表：

```bash
python3 scripts/setup-grok-composer.py --lang auto --table md
```

### 自动流程

```text
install-grok → fix-path → grok-login → configure-models → sync-opencode
```

| 步骤 | 说明 |
|------|------|
| `install-grok` | 未安装则安装 Grok Build CLI |
| `fix-path` | 将 `~/.grok/bin` 加入 PATH |
| `grok-login` | OAuth 登录；未完成授权不算硬错误 |
| `configure-models` | 默认模型 → `grok-composer-2.5-fast` |
| `sync-opencode` | 写入 `opencode.json` + OAuth 迁移 |

### 命令行参数

| 参数 | 说明 |
|------|------|
| `--lang auto\|zh\|en` | 输出语言（默认 `auto`） |
| `--table ascii\|md` | 结果表格式（默认 `ascii`） |
| `--user-message TEXT` | 可选，从用户消息推断语言 |

### 退出码

| 码 | 含义 |
|----|------|
| `0` | 完成，或表中列出待办项 |
| `1` | 硬错误（安装 / 脚本失败） |

### 目录结构

```text
opencode-grok-composer-setup/
├── SKILL.md                 # Grok Skill 说明（英文）
├── README.md                # 本文件（EN / 中文）
├── scripts/
│   ├── setup-grok-composer.py   # 主入口
│   ├── discover-xai-models.py   # Grok → OpenCode 模型同步
│   ├── migrate-grok-oauth.py    # OAuth 凭证迁移
│   └── i18n.py                  # 双语文案
```

### 许可证

MIT — 见 [LICENSE](LICENSE)。