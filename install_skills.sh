#!/usr/bin/env sh
# Install (copy) the four Whetstone skills into a skills-directory host.
#   DeepSeek Harness (dsh):  ./install_skills.sh ~/.agents/skills          (global)
#                            ./install_skills.sh <project>/.agents/skills  (project; needs .git)
#   Claude Code personal:    ./install_skills.sh ~/.claude/skills
# Add --link to symlink instead of copy (handy while developing; not every host follows symlinks).
set -e
TARGET="${1:?usage: install_skills.sh <skills-dir> [--link]}"
MODE="${2:-copy}"
SRC="$(cd "$(dirname "$0")" && pwd)/plugin/skills"
mkdir -p "$TARGET"
for skill in guide outline learn clarify; do
  rm -rf "$TARGET/$skill"
  if [ "$MODE" = "--link" ]; then
    ln -s "$SRC/$skill" "$TARGET/$skill"
  else
    cp -R "$SRC/$skill" "$TARGET/$skill"
    find "$TARGET/$skill" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
  fi
  echo "installed $skill -> $TARGET/$skill"
done
echo "Restart the host so it rediscovers skills; then type / and look for guide, outline, learn, clarify."
