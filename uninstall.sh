#!/usr/bin/env bash
# inquirist entfernen. Verlauf (~/.local/state/inquirist) geht mit.
set -euo pipefail
RICE="$HOME/.local/share/rice-apps"
"$HOME/.local/bin/inquirist" --quit 2>/dev/null || true
pkill -u "$(id -u)" -f "share/inquirist/inquirist.py" 2>/dev/null || true
rm -rf "$HOME/.local/share/inquirist" "$HOME/.local/state/inquirist"
rm -f "$HOME/.local/bin/inquirist" "$HOME/.local/share/applications/inquirist.desktop" \
      "$HOME/.local/share/icons/hicolor/scalable/apps/inquirist.svg" "$HOME/.config/autostart/inquirist.desktop" \
      "$HOME/.cache/inquirist-zeichen.tsv"
# gemeinsame Bausteine nur entfernen, wenn keine andere Suite-App sie noch braucht
if [ ! -d "$RICE/calendar" ] && [ ! -d "$RICE/music" ] && [ ! -d "$HOME/.local/share/mailist" ] \
   && [ ! -d "$HOME/.local/share/wallist" ] && [ ! -d "$HOME/.local/share/sharist" ] && [ ! -d "$HOME/.local/share/linguist" ]; then
    rm -rf "$RICE/fonts" "$RICE/tui.py" "$RICE/glass.py" "$RICE/istheme.py" "$RICE/changelog.py" "$RICE/swipe.py" "$RICE/__pycache__"
    rmdir "$RICE" 2>/dev/null || true
fi
echo "inquirist entfernt."
