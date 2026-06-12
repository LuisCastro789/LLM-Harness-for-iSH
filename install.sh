#!/bin/sh
# ish-harness installer for iSH (Alpine Linux, i686, musl libc)
# Usage:  sh install.sh

set -e

echo ""
echo "╭─────────────────────────────────────────╮"
echo "│        ish-harness  installer           │"
echo "╰─────────────────────────────────────────╯"
echo ""

# ── check Python ────────────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
    echo "Python3 not found. Installing..."
    apk add --no-cache python3 py3-pip
else
    PY_VER=$(python3 -c "import sys; print('%d.%d' % sys.version_info[:2])")
    echo "✓  Python $PY_VER found"
fi

# ── check pip ────────────────────────────────────────────────────────────────
if ! command -v pip3 >/dev/null 2>&1; then
    echo "pip3 not found. Installing..."
    apk add --no-cache py3-pip
else
    echo "✓  pip3 found"
fi

# ── optional: readline for command history ───────────────────────────────────
if python3 -c "import readline" 2>/dev/null; then
    echo "✓  readline available"
else
    echo "  readline not found — installing py3-readline..."
    apk add --no-cache py3-readline 2>/dev/null || true
fi

# ── tomli backport (needed on Python < 3.11) ─────────────────────────────────
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
if [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; then
    echo "  Python 3.$PY_MINOR detected — installing tomli backport..."
    pip3 install --break-system-packages tomli 2>/dev/null \
        || pip3 install tomli || true
fi

# ── install ish-harness ──────────────────────────────────────────────────────
echo ""
echo "Installing ish-harness..."
pip3 install --break-system-packages -e . 2>/dev/null \
    || pip3 install -e .

echo ""
echo "╭─────────────────────────────────────────╮"
echo "│  ✓  ish-harness installed successfully  │"
echo "╰─────────────────────────────────────────╯"
echo ""
echo "  Start:   harness"
echo "  Config:  ~/.harness/config.toml"
echo ""
echo "  Set your API key, then run:"
echo "    export OPENAI_API_KEY=sk-..."
echo "    harness"
echo ""
echo "  Or for HuggingFace / Gemma:"
echo "    export HF_TOKEN=hf_..."
echo "    harness"
echo "    ❯ /provider gemma"
echo ""
