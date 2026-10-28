#!/bin/bash
# Paste into the Claude Code cloud environment's "Setup script" field so every
# new session starts with the video toolchain ready. Self-contained on purpose:
# it does not rely on the repository being checked out yet.
set -e

# FFmpeg ships with the default image; install it only if a future image drops it.
command -v ffmpeg >/dev/null || (apt-get update -qq && apt-get install -y -qq ffmpeg)

# HyperFrames CLI, its headless Chrome and its Claude skills.
npm install -g hyperframes@0.8.214
hyperframes telemetry disable || true
hyperframes browser ensure
hyperframes skills update || echo "HyperFrames skills install failed, continuing"

# Remotion's Claude skills (remotion-best-practices and the rest of remotion-dev/skills).
DISABLE_TELEMETRY=1 npx --yes skills@1.7.4 add remotion-dev/skills --global --agent claude-code --skill '*' --yes --copy \
  || echo "Remotion skills install failed, continuing"

# Project dependencies, when the checkout is already in place.
for studio in /home/user/*/video-studio; do
  [ -d "$studio" ] || continue
  (cd "$studio/hyperframes" && npm ci --no-audit --no-fund)
  (cd "$studio/remotion" && npm ci --no-audit --no-fund)
done
