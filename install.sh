#!/usr/bin/env bash
set -e
echo "▸ Installing cursor-reset"
mkdir -p "$HOME/.cursor-reset"
curl -fsSL https://raw.githubusercontent.com/awaisdev5765/cursor-reset/main/cursor_reset.py -o "$HOME/.cursor-reset/cursor_reset.py"
chmod +x "$HOME/.cursor-reset/cursor_reset.py"
# alias for bash/zsh
for RC in "$HOME/.zshrc" "$HOME/.bashrc"; do
  if [ -f "$RC" ] && ! grep -q "alias cursor-reset" "$RC" 2>/dev/null; then
    echo "alias cursor-reset='python3 $HOME/.cursor-reset/cursor_reset.py'" >> "$RC"
    echo "  ✓ alias added to $RC"
  fi
done
echo "✔ installed. run: cursor-reset status  (or: python3 ~/.cursor-reset/cursor_reset.py status)"
