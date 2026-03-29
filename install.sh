#!/usr/bin/env bash
# install.sh — Install the /read-paper skill for Claude Code
# Works on Mac, Linux, and Windows (Git Bash)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS_DIR="$HOME/.claude/tools"
COMMANDS_DIR="$HOME/.claude/commands"
CONFIG_FILE="$TOOLS_DIR/mineru_config.json"

# --- Colors (if terminal supports them) ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo ""
echo "=== /read-paper skill installer ==="
echo ""

# --- 1. Check Python ---
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    error "Python not found. Install Python 3.9+ from https://python.org"
fi

PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]); then
    error "Python 3.9+ required (found $PY_VERSION)"
fi
info "Python $PY_VERSION"

# --- 2. Create directories ---
mkdir -p "$TOOLS_DIR"
mkdir -p "$COMMANDS_DIR"
info "Directories ready"

# --- 3. Copy files ---
copy_file() {
    local src="$1" dst="$2" name="$3"
    if [ -f "$dst" ]; then
        # Check if files are identical
        if diff -q "$src" "$dst" &>/dev/null; then
            info "$name already up to date"
            return
        fi
        echo ""
        warn "$name already exists at $dst"
        read -r -p "    Overwrite? [y/N] " response
        case "$response" in
            [yY][eE][sS]|[yY]) ;;
            *) warn "Skipping $name"; return ;;
        esac
    fi
    cp "$src" "$dst"
    info "$name installed"
}

copy_file "$SCRIPT_DIR/pdf_to_md.py" "$TOOLS_DIR/pdf_to_md.py" "pdf_to_md.py"
copy_file "$SCRIPT_DIR/read-paper.md" "$COMMANDS_DIR/read-paper.md" "read-paper.md"

# --- 4. Install Python dependencies ---
echo ""
$PYTHON -m pip install -q -r "$SCRIPT_DIR/requirements.txt" 2>/dev/null \
    || $PYTHON -m pip install -q requests 2>/dev/null \
    || warn "Could not install 'requests' automatically. Run: pip install requests"
info "Python dependencies OK"

# --- 5. API key setup ---
echo ""
if [ -f "$CONFIG_FILE" ]; then
    info "MinerU API key already configured"
else
    echo "You need a MinerU API key to convert PDFs."
    echo "Get one free at: https://mineru.net"
    echo ""
    read -r -p "Paste your MinerU API key (or press Enter to skip): " api_key
    if [ -n "$api_key" ]; then
        echo "{\"api_key\": \"$api_key\"}" > "$CONFIG_FILE"
        info "API key saved to $CONFIG_FILE"
    else
        warn "Skipped. Set it later:"
        echo "    Option A: export MINERU_API_KEY=\"your-key\""
        echo "    Option B: echo '{\"api_key\": \"your-key\"}' > $CONFIG_FILE"
    fi
fi

# --- 6. Verify ---
echo ""
$PYTHON -c "import py_compile; py_compile.compile('$TOOLS_DIR/pdf_to_md.py', doraise=True)" 2>/dev/null \
    && info "Script compiles OK" \
    || warn "Script has syntax errors — check your Python version"

echo ""
echo "=== Installation complete ==="
echo ""
echo "Usage in Claude Code:"
echo "  /read-paper path/to/paper.pdf"
echo "  /read-paper https://example.com/paper.pdf"
echo ""
echo "To update later: git pull && bash install.sh"
echo ""
