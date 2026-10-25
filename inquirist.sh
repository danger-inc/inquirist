#!/usr/bin/env bash
# Starter für inquirist (Super+R). Läuft es schon im Hintergrund, geht der Aufruf direkt per D-Bus hin.
#   inquirist [apps|fenster|dateien|rechner|ablage|zeichen|web|system]  ·  --daemon (Autostart)  ·  --hide  ·  --quit
APP=de.invincible.Inquirist
OBJ=/de/invincible/Inquirist
D="${INQUIRIST_DIR:-$HOME/.local/share/inquirist}"
PY=python3
LOG="${XDG_RUNTIME_DIR:-/tmp}/inquirist.log"

running() { gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
    --method org.freedesktop.DBus.NameHasOwner "$APP" 2>/dev/null | grep -q true; }
action() { gdbus call --session --timeout 3 --dest "$APP" --object-path "$OBJ" \
    --method org.gtk.Actions.Activate "$1" "${2:-[]}" '{}' >/dev/null 2>&1; }

layer_shell() {
    local p
    for p in /usr/lib/libgtk4-layer-shell.so.0 /usr/lib64/libgtk4-layer-shell.so.0 \
             /usr/lib/*-linux-gnu/libgtk4-layer-shell.so.0 /usr/local/lib/libgtk4-layer-shell.so.0 \
             /usr/local/lib/*-linux-gnu/libgtk4-layer-shell.so.0 /usr/local/lib64/libgtk4-layer-shell.so.0 \
             /usr/lib/libgtk4-layer-shell.so; do
        [[ -e $p ]] && { echo "$p"; return; }
    done
}
start() {
    local pre; pre=$(layer_shell)
    [[ -n ${WAYLAND_DISPLAY:-} && -n $pre ]] && export LD_PRELOAD=$pre${LD_PRELOAD:+:$LD_PRELOAD}
    if [[ $pre == /usr/local/* ]]; then
        local d=${pre%/*}/girepository-1.0
        [[ -d $d ]] && export GI_TYPELIB_PATH=$d${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}
    fi
    setsid -f "$PY" "$D/inquirist.py" "$@" >>"$LOG" 2>&1 </dev/null
}

case "${1:-}" in
    --daemon) running || start --daemon; exit 0 ;;
    --quit)   running && action quit; exit 0 ;;
    --hide)   running && action hide; exit 0 ;;
    *)        m=${1:-}
              running && action show "[<'$m'>]" && exit 0
              start "$m"; exit 0 ;;
esac
