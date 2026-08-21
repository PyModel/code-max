#!/usr/bin/env bash
# Symlink this skill into every agent that reads a skills directory.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="$(basename "$SRC")"

TARGETS=(
  "$HOME/.claude/skills"
  "$HOME/.codex/skills"
  "$HOME/.cursor/skills"
  "$HOME/.gemini/skills"
  "$HOME/.pi/skills"
  "$HOME/.config/opencode/skills"
)

for dir in "${TARGETS[@]}"; do
  mkdir -p "$dir"
  ln -sfn "$SRC" "$dir/$NAME"
  echo "linked $dir/$NAME"
done
