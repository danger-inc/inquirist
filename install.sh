#!/usr/bin/env bash
# inquirist installieren (ins eigene Benutzerverzeichnis, root nur für Systempakete).
#   ./install.sh            normal (fragt nach Systempaketen und Autostart)
#   ./install.sh --update   ohne Rückfragen (von update.sh)
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SRC/pkg.sh"
DIR="$HOME/.local/share/inquirist"
RICE="$HOME/.local/share/rice-apps"
BIN="$HOME/.local/bin"
APPS="$HOME/.local/share/applications"
ICONS="$HOME/.local/share/icons/hicolor/scalable/apps"
UPDATE=0; [[ "${1:-}" == "--update" ]] && UPDATE=1

say "== inquirist installieren =="
basics_missing() {
    python3 -c 'import gi, cairo; gi.require_version("Gtk", "4.0")' 2>/dev/null && return 1
    return 0
}
if { (( UPDATE )) && basics_missing && say "Es fehlen Systempakete – werden nachinstalliert …"; } \
   || ask "Systempakete installieren (GTK4, PyGObject, gtk4-layer-shell, qalc, cliphist, wl-clipboard)?"; then
    pkg_install \
        "gtk4 gtk4-layer-shell python python-gobject python-cairo adwaita-icon-theme xdg-utils wl-clipboard libqalculate cliphist libnotify" \
        "python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-gtk4layershell-1.0 libgtk4-layer-shell0 adwaita-icon-theme xdg-utils libglib2.0-bin wl-clipboard qalc cliphist libnotify-bin" \
        "python3 python3-gobject python3-cairo gtk4 gtk4-layer-shell adwaita-icon-theme xdg-utils glib2 wl-clipboard libqalculate cliphist libnotify" \
        "python3 python3-gobject python3-gobject-cairo python3-gobject-Gdk typelib-1_0-Gtk-4_0 typelib-1_0-Gtk4LayerShell-1_0 adwaita-icon-theme xdg-utils glib2-tools wl-clipboard qalculate libnotify-tools" \
        || warn "Paketinstallation nicht vollständig – weiter."
fi
echo

say "Kopiere inquirist nach $DIR …"
mkdir -p "$DIR" "$RICE/fonts" "$BIN" "$APPS" "$ICONS"
cp -f "$SRC"/app/inquirist/*.py "$SRC"/app/inquirist/VERSION "$SRC"/app/inquirist/CHANGELOG.md "$DIR/"
install -m 755 "$SRC/inquirist.sh" "$DIR/inquirist.sh"
chmod +x "$DIR/inquirist.py"
cp -f "$SRC/app/tui.py" "$SRC/app/glass.py" "$SRC/app/changelog.py" "$SRC/app/swipe.py" "$RICE/"   # gemeinsame Bausteine
cp -f "$SRC"/app/fonts/* "$RICE/fonts/"                           # Symbolschrift (Icons ohne Nerd Font)
ln -sf "$DIR/inquirist.sh" "$BIN/inquirist"
sed "s|@EXEC@|$BIN/inquirist|g" "$SRC/inquirist.desktop.in" > "$APPS/inquirist.desktop"
cp -f "$SRC/inquirist.svg" "$ICONS/inquirist.svg"
refresh_desktop

if (( ! UPDATE )); then
    echo
    if ask "inquirist beim Anmelden unsichtbar starten? (dann ist es beim Tastendruck sofort da)"; then
        mkdir -p "$HOME/.config/autostart"
        sed -e "s|@EXEC@|$BIN/inquirist --daemon|" -e "s|^Name=inquirist|Name=inquirist (Hintergrund)|" \
            "$SRC/inquirist.desktop.in" > "$HOME/.config/autostart/inquirist.desktop"
        echo "  Autostart: ~/.config/autostart/inquirist.desktop"
        echo "  (Hyprland/Sway lesen den Ordner nicht – dort selbst eintragen:  exec-once = inquirist --daemon)"
    fi
fi
# läuft inquirist schon im Hintergrund? → neu starten, damit der neue Code gilt
if gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
     --method org.freedesktop.DBus.NameHasOwner de.invincible.Inquirist 2>/dev/null | grep -q true; then
    "$BIN/inquirist" --quit; sleep 1.5; "$BIN/inquirist" --daemon
fi

echo
say "Prüfe …"
check_gtk || warn "Ohne passendes GTK startet inquirist nicht – siehe README."
python3 -c 'import gi, cairo; gi.require_version("Gtk", "4.0")' 2>/dev/null && echo "  PyGObject/cairo: ok" \
    || warn "  PyGObject oder pycairo fehlt"
python3 - <<'PY'
try:
    import gi
    gi.require_version("Gtk4LayerShell", "1.0")
    print("  gtk4-layer-shell: ok – inquirist erscheint als Ebene über allem")
except (ImportError, ValueError):
    print("  gtk4-layer-shell: fehlt – inquirist öffnet dann als normales Fenster (ohne Klick-daneben-schließen)")
PY
for c in qalc cliphist wl-copy notify-send; do
    command -v "$c" >/dev/null && echo "  $c: vorhanden" || echo "  $c: fehlt – optional (rechner / ablage / kopieren / meldungen)"
done
[[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]] || echo "  hinweis: die Fensterliste gibt es nur unter Hyprland"
echo
path_hint
say "Fertig!  Starten mit:  inquirist   (oder über das Anwendungsmenü)"
echo "Tastenkürzel auf  inquirist  legen (Hyprland:  bind = SUPER, R, exec, inquirist ); direkt in einen Modus:"
echo "  inquirist fenster | dateien | rechner | ablage | zeichen | web | system"
echo "Hyprland, für Weichzeichner:  layerrule = blur, inquirist  und  layerrule = ignorealpha 0.1, inquirist"
echo "Aktualisieren: ./update.sh   Entfernen: ./uninstall.sh"
