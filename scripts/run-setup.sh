#!/usr/bin/env sh
# Pick python3 or python (Python 3.10+ required).
set -e
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$SCRIPT_DIR/setup-grok-composer.py" "$@"
fi
if command -v python >/dev/null 2>&1; then
  exec python "$SCRIPT_DIR/setup-grok-composer.py" "$@"
fi
echo "Python 3 not found (tried python3, python)" >&2
exit 1