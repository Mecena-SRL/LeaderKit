#!/bin/bash
# Sessioni cloud di Claude Code: lua5.4 e dipendenze dei test (pytest, pyflakes, Pillow, numpy).
set -euo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
if ! command -v lua5.4 >/dev/null 2>&1; then
  (apt-get update -qq && apt-get install -y -qq lua5.4) >/dev/null 2>&1 || echo "lua5.4 non installato: i test Lua verranno saltati"
fi
python3 -m pip install -q pytest pyflakes pillow numpy >/dev/null 2>&1 || echo "pip install non riuscito"
