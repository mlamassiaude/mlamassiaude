#!/usr/bin/env bash
# Installs everything video-studio needs. Safe to re-run: each step skips what is already there.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HF_VERSION="0.8.214"

say() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

say "Node.js (needs 22 or newer)"
if ! command -v node >/dev/null || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 22 ]; then
  echo "Node.js 22+ is required. Install it from https://nodejs.org or with nvm, then re-run." >&2
  exit 1
fi
node -v

say "FFmpeg and FFprobe"
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null; then
  if command -v apt-get >/dev/null; then
    SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
    $SUDO apt-get update -qq && $SUDO apt-get install -y -qq ffmpeg
  elif command -v brew >/dev/null; then
    brew install ffmpeg
  else
    echo "Install FFmpeg with your package manager, then re-run." >&2
    exit 1
  fi
fi
ffmpeg -hide_banner -version | head -1

say "HyperFrames CLI ${HF_VERSION}"
if [ "$(hyperframes --version 2>/dev/null | grep -o '[0-9.]*' | head -1)" != "$HF_VERSION" ]; then
  npm install -g "hyperframes@${HF_VERSION}"
fi
hyperframes telemetry disable >/dev/null 2>&1 || true
(cd "$ROOT/hyperframes" && npm install --no-audit --no-fund)

say "Chrome Headless Shell for HyperFrames"
hyperframes browser ensure

say "HyperFrames agent skills (hyperframes, hyperframes-cli, hyperframes-registry, media-use)"
if [ ! -d "$HOME/.claude/skills/hyperframes" ]; then
  hyperframes skills update || echo "Skill install failed; run 'hyperframes skills update' later."
fi

say "Remotion agent skills (remotion-dev/skills)"
if [ ! -d "$HOME/.claude/skills/remotion-best-practices" ]; then
  DISABLE_TELEMETRY=1 npx --yes skills@1.7.4 add remotion-dev/skills --global --agent claude-code --skill '*' --yes --copy \
    || echo "Skill install failed; run 'npx skills add remotion-dev/skills' later."
fi

say "Remotion project dependencies"
(cd "$ROOT/remotion" && npm install --no-audit --no-fund)

say "Chrome Headless Shell for Remotion"
# remotion.config.ts reuses an existing headless shell when it finds one, so this
# download only matters on machines without Playwright or HyperFrames' copy.
(cd "$ROOT/remotion" && npx remotion browser ensure) \
  || echo "Remotion's browser download failed; renders will use the headless shell found by remotion.config.ts."

say "Done. Run scripts/verify.sh to test every part of the toolchain."
