#!/usr/bin/env sh
# anzuelo installer - https://github.com/bberastegui/anzuelo
# Usage: curl -fsSL https://raw.githubusercontent.com/bberastegui/anzuelo/main/install.sh | sh

set -e

REPO="bberastegui/anzuelo"
BINARY_NAME="anzuelo"
INSTALL_DIR="${ANZUELO_INSTALL_DIR:-$HOME/.local/bin}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { printf "${GREEN}[INFO]${NC} %s\n" "$1"; }
warn()  { printf "${YELLOW}[WARN]${NC} %s\n" "$1"; }
error() { printf "${RED}[ERROR]${NC} %s\n" "$1"; exit 1; }

detect_os() {
  case "$(uname -s)" in
    Linux*)  OS="linux";;
    Darwin*) OS="darwin";;
    *)       error "Unsupported OS: $(uname -s)";;
  esac
}

detect_arch() {
  case "$(uname -m)" in
    x86_64|amd64)  ARCH="x86_64";;
    arm64|aarch64) ARCH="aarch64";;
    *)             error "Unsupported arch: $(uname -m)";;
  esac
}

get_latest_version() {
  VERSION=$(curl -sI "https://github.com/${REPO}/releases/latest" \
    | grep -i '^location:' \
    | sed -E 's|.*/tag/([^[:space:]]+).*|\1|' \
    | tr -d '\r')

  if [ -z "$VERSION" ]; then
    warn "Redirect lookup failed, falling back to GitHub API..."
    VERSION=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
      | grep '"tag_name":' \
      | sed -E 's/.*"([^"]+)".*/\1/')
  fi

  if [ -z "$VERSION" ]; then
    error "Failed to get latest version (set ANZUELO_VERSION=vX.Y.Z to pin)"
  fi
}

install_via_pip() {
  info "Installing via pip..."
  if command -v pip3 >/dev/null 2>&1; then
    pip3 install --user anzuelo 2>/dev/null && return 0
    pip3 install --user "$1" 2>/dev/null && return 0
  fi
  if command -v pip >/dev/null 2>&1; then
    pip install --user anzuelo 2>/dev/null && return 0
    pip install --user "$1" 2>/dev/null && return 0
  fi
  return 1
}

install_from_source() {
  info "Installing from source..."
  local srcdir="$1"
  if command -v pip3 >/dev/null 2>&1; then
    pip3 install --user -e "$srcdir"
  elif command -v pip >/dev/null 2>&1; then
    pip install --user -e "$srcdir"
  else
    error "pip not found. Install Python 3 from https://python.org"
  fi
}

setup_hooks() {
  rc_file="${ANZUELO_RC:-}"
  if [ -z "$rc_file" ]; then
    case "${SHELL:-}" in
      *zsh*)  rc_file="${ZDOTDIR:-$HOME}/.zshrc" ;;
      *bash*) rc_file="${HOME}/.bashrc" ;;
      *)      rc_file="";;
    esac
  fi

  if [ -n "$rc_file" ]; then
    if grep -q "anzuelo init" "$rc_file" 2>/dev/null; then
      info "anzuelo hooks already in $rc_file"
    else
      {
        echo ""
        echo "# anzuelo: AI coding assistant metrics"
        echo 'eval "$(anzuelo init)"'
      } >> "$rc_file"
      info "Added anzuelo init to $rc_file"
      info "Run: source $rc_file"
    fi
  else
    warn "Add this to your shell profile:"
    warn '  eval "$(anzuelo init)"'
  fi
}

main() {
  echo ""
  printf "  ${GREEN}anzuelo${NC} — lightweight AI coding metrics\n"
  echo "  ────────────────────────────────────────"
  echo ""

  # Check Python
  if ! command -v python3 >/dev/null && ! command -v python >/dev/null; then
    error "Python 3 is required. Install from https://python.org"
  fi

  # Try installing from local source, PyPI, or GitHub
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd 2>/dev/null || echo "")"

  if [ -n "$SCRIPT_DIR" ] && [ -f "$SCRIPT_DIR/pyproject.toml" ]; then
    install_from_source "$SCRIPT_DIR"
  elif [ -n "$ANZUELO_VERSION" ]; then
    TMP="$(mktemp -d)"
    URL="https://github.com/${REPO}/archive/${ANZUELO_VERSION}.tar.gz"
    info "Downloading from $URL"
    curl -fsSL "$URL" -o "$TMP/release.tar.gz"
    tar -xzf "$TMP/release.tar.gz" -C "$TMP"
    install_from_source "$TMP"/*/
    rm -rf "$TMP"
  elif command -v anzuelo >/dev/null 2>&1; then
    info "anzuelo already installed: $(anzuelo --version 2>/dev/null || echo 'present')"
  else
    pip_pkg="${ANZUELO_PIP_PKG:-anzuelo}"
    install_via_pip "$pip_pkg" || error "pip install failed. Try: pip install anzuelo"
  fi

  # Verify
  if command -v anzuelo >/dev/null 2>&1; then
    info "Installed: $(anzuelo --version 2>/dev/null || command -v anzuelo)"
  else
    if python3 -m anzuelo --version >/dev/null 2>&1; then
      warn "Add to your shell profile:"
      warn '  alias anzuelo="python3 -m anzuelo"'
    else
      error "Installation failed. Try: pip install anzuelo"
    fi
  fi

  echo ""
  info "Setting up shell hooks..."
  setup_hooks

  # Install hooks for detected harnesses
  if command -v anzuelo >/dev/null 2>&1; then
    echo ""
    info "Installing hooks for detected AI coding harnesses..."
    anzuelo init --all 2>&1 || true
  fi

  echo ""
  info "Installation complete!"
  echo ""
  echo "  Quick start:"
  echo "    1. source ${rc_file:-~/.bashrc}"
  echo "    2. anzuelo status"
  echo "    3. anzuelo run -- <command>"
  echo "    4. anzuelo report"
  echo ""
  info "To uninstall:"
  echo "    1. anzuelo uninstall --all    (remove harness hooks)"
  echo "    2. anzuelo uninstall --global (remove shell hooks)"
  echo "    3. anzuelo uninstall --data   (remove metrics database)"
  echo "    4. pip uninstall anzuelo"
  echo ""
}

main
