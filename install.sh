#!/usr/bin/env bash
# cursor-reset installer — macOS / Linux
#   curl -fsSL https://raw.githubusercontent.com/Awaisdev01/cursor-reset/main/install.sh | bash
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

print_logo() {
    echo -e "${CYAN}"
    cat << "EOF"
   ██████╗██╗   ██╗██████╗ ███████╗ ██████╗ ██████╗       ██████╗██████╗
  ██╔════╝██║   ██║██╔══██╗██╔════╝██╔═══██╗██╔══██╗     ██╔════╝██╔══██╗
  ██║     ██║   ██║██████╔╝███████╗██║   ██║██████╔╝     ██║     ██████╔╝
  ██║     ██║   ██║██╔══██╗╚════██║██║   ██║██╔══██╗     ██║     ██╔══██╗
  ╚██████╗╚██████╔╝██║  ██╗███████║╚██████╔╝██║  ██╗     ╚██████╗██║  ██╗
   ╚═════╝ ╚═════╝ ╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═╝      ╚═════╝╚═╝  ╚═╝
EOF
    echo -e "${NC}"
    echo -e "  ${GREEN}Survive Cursor trial limits on one machine${NC}"
    echo
}

print_logo

DEST="$HOME/.cursor-reset"
mkdir -p "$DEST"
echo -e "${CYAN}▸ downloading cursor_reset.py${NC}"
curl -fsSL https://raw.githubusercontent.com/Awaisdev01/cursor-reset/main/cursor_reset.py -o "$DEST/cursor_reset.py"
chmod +x "$DEST/cursor_reset.py"
echo -e "${GREEN}✓ $DEST/cursor_reset.py${NC}"

# shell aliases
RC=""
[ -f "$HOME/.zshrc" ] && RC="$HOME/.zshrc"
[ -z "$RC" ] && [ -f "$HOME/.bashrc" ] && RC="$HOME/.bashrc"
if [ -n "$RC" ] && ! grep -q "cursor-reset" "$RC" 2>/dev/null; then
  cat >> "$RC" << 'ALIASES'

# cursor-reset
alias cursor-reset='python3 $HOME/.cursor-reset/cursor_reset.py'
alias cursor-reset-auto='python3 $HOME/.cursor-reset/cursor_reset.py auto'
ALIASES
  echo -e "${GREEN}✓ aliases added to $RC${NC}"
  echo -e "${YELLOW}  (run: source $RC  — or open a new terminal)${NC}"
fi

echo
echo -e "${GREEN}✔ installed.${NC}"
echo -e "  Try it:      ${CYAN}cursor-reset${NC}          (interactive menu)"
echo -e "  One shot:    ${CYAN}cursor-reset reset${NC}    (rotate device IDs)"
echo -e "  Always-on:   ${CYAN}cursor-reset-auto${NC}     (watch + auto-reset)"
echo
echo -e "${YELLOW}  Usage limits are Cursor's ToS to enforce — use for genuine trial"
echo -e "  evaluation on your own machine.${NC}"
