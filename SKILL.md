---
name: opencode-grok-composer-setup
description: >
  Configure OpenCode to use Grok Composer (and Build) via OAuth. Silent auto
  pipeline; one result table at the end. Triggers: "配置 opencode grok composer",
  "opencode grok composer", "opencode composer", "sync grok composer to opencode",
  "/opencode-grok-composer-setup"
metadata:
  short-description: "Configure OpenCode Grok Composer (OAuth)"
---

# OpenCode ← Grok Composer

## What the AI should do

Run once, stay silent during execution, and **paste only the script’s final output**:

```bash
python3 "{SKILL_DIR}/scripts/setup-grok-composer.py" --lang auto
```

For chat, use a Markdown table: `--table md`

## Automatic pipeline

Install Grok → PATH → `grok login` (wait for browser confirmation) → Composer default model → sync OpenCode

- Do not change OpenCode’s top-level `model`
- Not logged in is not a run error; the pipeline still completes
- Only Grok CLI auth prints a link or device code

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Done (or pending items listed in the table) |
| `1` | Real run error (install / script failure) |