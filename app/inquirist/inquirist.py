#!/usr/bin/env python3
# inquirist: der Starter der Suite (Super+R) – Programme, Fenster, Dateien, Rechner, Zwischenablage, Zeichen, Web, System.
# Läuft unsichtbar im Hintergrund (--daemon) und blendet sich auf Tastendruck sofort ein; Eingaben sind nie blockiert
# (alles Langsame läuft in Threads). Ebene (layer-shell) statt Fenster: kein Kacheln, kein Arbeitsflächenwechsel.
#   inquirist [modus]         zeigen (oder umschalten / schließen, wenn schon offen)
#   inquirist --daemon        nur im Hintergrund starten      inquirist --quit
# Modi: apps fenster dateien rechner ablage zeichen web system
import os, sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, os.path.expanduser("~/.local/share/rice-apps"))

PRELOADED = "gtk4-layer-shell" in os.environ.get("LD_PRELOAD", "")
os.environ.setdefault("GSK_RENDERER", "cairo")      # gleiche Optik, halber Speicher, schnellerer Start

import gi  # noqa: E402
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Pango  # noqa: E402

for _var in ("LD_PRELOAD", "GSK_RENDERER"):       # nicht an gestartete Programme vererben
    os.environ.pop(_var, None)

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell as Layer
except (ImportError, ValueError):
    Layer = None

import tui  # noqa: E402
import providers as P  # noqa: E402

APP_ID = "de.invincible.Inquirist"
TOP_MARGIN = 118           # Abstand vom oberen Bildschirmrand (unter der Waybar), wie der alte Starter
SUP = "¹²³⁴⁵⁶⁷⁸⁹"
LINES = 9

CSS = """
window.iq-win { background: none; background-color: transparent; box-shadow: none; }
window.iq-win { background-color: rgba(0, 0, 0, 0.04); }
window.iq-win * { font-family: "JetBrainsMono Nerd Font", "Notes Icons", monospace; font-weight: bold; font-size: 11pt; }
.iq-panel { background-color: alpha(@background, 0.85); border: 1px solid alpha(@primary, 0.55); border-radius: 6px; }
.iq-head { padding: 10px 14px 6px 14px; }
.iq-brand { background-color: @primary; color: @on_primary; padding: 2px 9px; border-radius: 4px; }
button.iq-tab { background: none; border: none; box-shadow: none; outline: none; min-height: 0; min-width: 0;
    padding: 2px 5px; border-radius: 4px; color: alpha(@foreground, 0.6); }
button.iq-tab:hover { background-color: alpha(@primary, 0.12); color: @foreground; }
button.iq-tab.sel { background-color: alpha(@primary, 0.22); color: @foreground; }
.iq-input { margin: 4px 14px 8px 14px; padding: 6px 10px; border: 1px solid alpha(@primary, 0.55); border-radius: 4px;
    background-color: alpha(@background, 0.30); }
.iq-prompt { color: @primary; }
text.iq-text { background: none; color: @foreground; caret-color: @primary; min-height: 0; padding: 0; outline: none; }
text.iq-text > placeholder { color: alpha(@foreground, 0.5); }
.iq-count { color: alpha(@foreground, 0.55); }
.iq-msg { margin: 0 14px 8px 14px; padding: 6px 10px; border: 1px dashed alpha(@primary, 0.55); border-radius: 4px; }
button.iq-crumb { background: none; border: none; box-shadow: none; padding: 1px 6px; min-height: 0; min-width: 0;
    border-radius: 4px; color: alpha(@foreground, 0.75); outline: none; }
button.iq-crumb:hover { background-color: alpha(@primary, 0.16); color: @foreground; }
.iq-sep { color: alpha(@foreground, 0.4); }
.iq-list { margin: 0 8px; background: none; }
.iq-list > listview, listview.iq-lv { background: none; }
listview.iq-lv > row { border-radius: 4px; padding: 0; margin: 1px 0; outline: none; background: none; color: @foreground; }
listview.iq-lv > row:hover { background-color: alpha(@primary, 0.1); }
listview.iq-lv > row:selected { background-color: alpha(@primary, 0.22); color: @foreground; }
.iq-row { padding: 5px 10px; }
.iq-row > * { min-height: 22px; }
.iq-row .glyph { color: @secondary; font-size: 15px; min-width: 22px; }
.iq-row .glyph.char { font-size: 17px; color: @foreground; }
.iq-row .sub { color: alpha(@foreground, 0.55); }
.iq-row .meta { color: @secondary; font-size: 10pt; font-weight: normal; }
listview.iq-lv > row:selected .meta { color: alpha(@foreground, 0.85); }
.iq-list scrollbar { background: none; border: none; }
.iq-list scrollbar slider { background-color: alpha(@primary, 0.4); min-width: 3px; border-radius: 2px; }
.iq-foot { padding: 8px 14px 10px 14px; color: @primary; font-size: 9pt; }
.iq-empty { color: alpha(@foreground, 0.5); }
.g-dir { color: @primary; }
.g-img { color: @tertiary; } .g-vid { color: @tertiary; } .g-aud { color: @secondary; }
.g-doc { color: @secondary; } .g-txt { color: alpha(@foreground, 0.75); } .g-arc { color: @tertiary; }
.g-code { color: @primary; } .g-exe { color: @primary; } .g-font { color: @secondary; } .g-key { color: @tertiary; }
.g-link { color: @secondary; } .g-file { color: alpha(@foreground, 0.6); }
.iq-row .fhidden { opacity: 0.6; }
.iq-row .flink { font-style: italic; }
"""


class Inquirist(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.win = None
        self.start_mode = None
        self.daemon = False
        self.history = P.History()
        self.modes = []
        self.mode = None
        self.tabs = []
        self._crumb_key = None

    # ================= Start =================
    def do_startup(self):
        Gtk.Application.do_startup(self)
        tui.load_icon_font()
        if CSS not in tui.CSS:
            tui.CSS += CSS
        tui.Theme.get().load()
        for name, cb, pt in (("show", lambda a, v: self.show_mode(v.get_string() if v else ""), "s"),
                             ("toggle", lambda a, v: self.show_mode(v.get_string() if v else "", toggle=True), "s"),
                             ("hide", lambda *_: self.hide(), None),
                             ("type", lambda a, v: self.set_query(v.get_string()), "s"),
                             ("enter", lambda *_: self.activate(self.sel.get_selected()), None), ("quit", lambda *_: self.quit(), None)):
            act = Gio.SimpleAction.new(name, GLib.VariantType.new(pt) if pt else None)
            act.connect("activate", cb)
            self.add_action(act)
        self.build()
        self.hold()                       # läuft auch ohne sichtbares Fenster weiter

    def do_activate(self):
        if self.start_mode is not None and not self.daemon:
            m, self.start_mode = self.start_mode, None
            self.show_mode(m)

    # ================= Aufbau =================
    def build(self):
        self.use_layer = bool(Layer and PRELOADED and Layer.is_supported())
        win = self.win = Gtk.Window(application=self, title="inquirist", resizable=bool(self.use_layer))
        win.add_css_class("iq-win")
        if not self.use_layer:
            win.set_default_size(820, -1)
        win.set_hide_on_close(True)
        self.backdrop = None
        if self.use_layer:
            Layer.init_for_window(win)
            Layer.set_namespace(win, "inquirist")
            Layer.set_layer(win, Layer.Layer.OVERLAY)
            for edge in (Layer.Edge.TOP, Layer.Edge.BOTTOM, Layer.Edge.LEFT, Layer.Edge.RIGHT):
                Layer.set_anchor(win, edge, True)             # ganze Fläche: Klick daneben schließt
            Layer.set_exclusive_zone(win, 0)                  # Waybar bleibt frei
            Layer.set_keyboard_mode(win, Layer.KeyboardMode.EXCLUSIVE)
            click = Gtk.GestureClick(button=0)
            click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            click.connect("pressed", self._outside_click)
            win.add_controller(click)
        else:
            win.set_decorated(False)
            win.connect("notify::is-active", lambda w, _p: None if w.is_active() or not w.get_visible() else self.hide())

        # Kopf: Marke + Reiter
        head = Gtk.Box(spacing=10)
        head.add_css_class("iq-head")
        brand = Gtk.Label(label="inquirist")
        brand.add_css_class("iq-brand")
        brand.set_valign(Gtk.Align.CENTER)
        head.append(brand)
        tabs = Gtk.Box(spacing=2, hexpand=True)
        head.append(tabs)
        for i, cls in enumerate(P.MODES):
            m = cls(self)
            self.modes.append(m)
            b = Gtk.Button(label=f"{SUP[i]}{m.label}", focusable=False, focus_on_click=False)
            b.add_css_class("iq-tab")
            b.connect("clicked", self._tab_clicked, i)
            tabs.append(b)
            self.tabs.append(b)

        # Eingabe
        inp = Gtk.Box(spacing=8)
        inp.add_css_class("iq-input")
        pr = Gtk.Label(label="›")
        pr.add_css_class("iq-prompt")
        inp.append(pr)
        self.text = Gtk.Text(hexpand=True, placeholder_text="suchen …")
        self.text.add_css_class("iq-text")
        self.text.connect("changed", lambda *_: self.refilter())
        inp.append(self.text)
        self.count = Gtk.Label(label="")
        self.count.add_css_class("iq-count")
        inp.append(self.count)

        # Hinweiszeile / Pfad
        self.msg = Gtk.Box(spacing=0)
        self.msg.add_css_class("iq-msg")
        self.msg.set_visible(False)

        # Liste
        self.store = Gio.ListStore.new(P.Item)
        self.sel = Gtk.SingleSelection(model=self.store, autoselect=True, can_unselect=False)
        fac = Gtk.SignalListItemFactory()
        fac.connect("setup", self._row_setup)
        fac.connect("bind", self._row_bind)
        self.lv = Gtk.ListView(model=self.sel, factory=fac, single_click_activate=True)
        self.lv.add_css_class("iq-lv")
        self.lv.connect("activate", lambda lv, pos: self.activate(pos))
        sc = Gtk.ScrolledWindow(child=self.lv, hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_height=LINES * 34 + 2,
                                max_content_height=LINES * 34 + 2, propagate_natural_height=False)
        sc.add_css_class("iq-list")
        sc.set_size_request(-1, LINES * 34 + 2)
        self.empty = Gtk.Label(label="keine treffer", valign=Gtk.Align.START, margin_top=16)
        self.empty.add_css_class("iq-empty")
        ov = Gtk.Overlay(child=sc)
        ov.add_overlay(self.empty)
        ov.set_size_request(-1, LINES * 34 + 2)

        self.foot = Gtk.Label(label="", xalign=1, use_markup=True)
        self.foot.add_css_class("iq-foot")

        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        panel.add_css_class("iq-panel")
        for w in (head, inp, self.msg, ov, self.foot):
            panel.append(w)
        self.panel = panel
        if self.use_layer:
            panel.set_size_request(820, -1)
            panel.set_halign(Gtk.Align.CENTER)
            panel.set_valign(Gtk.Align.START)
            panel.set_margin_top(TOP_MARGIN)
        win.set_child(panel)

        keys = Gtk.EventControllerKey(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._key)
        win.add_controller(keys)
        # Maus erst nach echter Bewegung wirksam (ruhender Zeiger unter der Liste darf nichts markieren/auslösen)
        self._mouse_ref = None
        mot = Gtk.EventControllerMotion(propagation_phase=Gtk.PropagationPhase.CAPTURE)
        mot.connect("motion", self._motion)
        win.add_controller(mot)
        self.set_mode(0, quiet=True)

    # ---- Zeilen
    def _row_setup(self, _f, li):
        box = Gtk.Box(spacing=10)
        box.add_css_class("iq-row")
        icon = Gtk.Image(pixel_size=22, valign=Gtk.Align.CENTER)
        glyph = Gtk.Label(valign=Gtk.Align.CENTER)
        glyph.add_css_class("glyph")
        title = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, use_markup=True)
        sub = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END, use_markup=True)
        sub.add_css_class("sub")
        meta = Gtk.Label(xalign=1)
        meta.add_css_class("meta")
        for w in (icon, glyph, title, sub, meta):
            box.append(w)
        li.set_child(box)

    def _row_bind(self, _f, li):
        it = li.get_item()
        box = li.get_child()
        icon = box.get_first_child()
        glyph = icon.get_next_sibling()
        title = glyph.get_next_sibling()
        sub = title.get_next_sibling()
        meta = sub.get_next_sibling()
        if it.icon is not None:
            if isinstance(it.icon, str):
                icon.set_from_icon_name(it.icon)
            else:
                icon.set_from_gicon(it.icon)
            icon.set_visible(True)
            glyph.set_visible(False)
        else:
            icon.set_visible(False)
            glyph.set_visible(bool(it.glyph))
            glyph.set_label(it.glyph)
            glyph.set_css_classes(["glyph"] + it.css.split())
        title.set_css_classes([c for c in it.css.split() if c in ("fhidden", "flink")])
        if it.markup:
            title.set_markup(it.title)
        else:
            title.set_label(it.title)
        title.set_hexpand(not it.sub)
        sub.set_visible(bool(it.sub))
        sub.set_markup(it.sub) if it.sub else None
        meta.set_visible(bool(it.meta))
        meta.set_label(it.meta)

    # ================= Zustand =================
    def launch_context(self):
        return Gdk.Display.get_default().get_app_launch_context()

    def say(self, text):
        self.msg_text(P.esc(text))

    def current(self):
        return self.sel.get_selected_item()

    def query(self):
        return self.text.get_text()

    def set_query(self, t):
        self.text.set_text(t)
        self.text.set_position(-1)

    def set_mode(self, i, quiet=False):
        self.mode = self.modes[i]
        for j, b in enumerate(self.tabs):
            (b.add_css_class if j == i else b.remove_css_class)("sel")
        self.text.set_placeholder_text(self.mode.placeholder)
        self.foot.set_markup(self._foot(self.mode.hint))
        self._crumb_key = None
        if not quiet:
            self.text.set_text("")
        self.mode.show()
        self.refilter()

    @staticmethod
    def _foot(hint):
        parts = [p for p in hint.split("   ") if p] + ["tab modus", "esc zu"]
        out = []
        for p in parts:
            k, _, rest = p.partition(" ")
            out.append(f"{P.esc(k)} <span alpha='55%'>{P.esc(rest)}</span>")
        return "   ".join(out)

    def msg_text(self, markup):
        self._crumb_key = None
        child = self.msg.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.msg.remove(child)
            child = nxt
        if markup:
            lab = Gtk.Label(label=markup, use_markup=True, xalign=0, hexpand=True, wrap=True)
            self.msg.append(lab)
        self.msg.set_visible(bool(markup))

    def msg_crumbs(self, parts, busy):
        key = (tuple(p[1] for p in parts), busy)
        if key == self._crumb_key:
            return
        self.msg_text("")
        self._crumb_key = key
        for n, (name, path) in enumerate(parts):
            if n:
                sep = Gtk.Label(label="›")
                sep.add_css_class("iq-sep")
                self.msg.append(sep)
            b = Gtk.Button(label=name, focusable=False, focus_on_click=False)
            b.add_css_class("iq-crumb")
            b.connect("clicked", lambda _b, p=path: self.mode.navigate(p))
            self.msg.append(b)
        if busy:
            sp = Gtk.Label(label="  lädt …", hexpand=True, xalign=1)
            sp.add_css_class("iq-sep")
            self.msg.append(sp)
        self.msg.set_visible(True)

    def refilter(self, keep=False):
        if self.mode is None:
            return
        prev = self.current().ident if keep and self.current() else None
        q = self.query()
        rows = self.mode.rows(q)
        self.store.splice(0, self.store.get_n_items(), rows)
        pos = 0
        if prev is not None:
            for n, r in enumerate(rows):
                if r.ident == prev:
                    pos = n
                    break
        if rows:
            self.sel.set_selected(pos)
            if pos == 0:
                self.lv.scroll_to(0, Gtk.ListScrollFlags.NONE, None)
        self.count.set_label(f"{len(rows)} / {self.mode.total()}")
        self.empty.set_visible(not rows and not self.mode.busy(q))
        m = self.mode.message(q)
        if isinstance(m, dict):
            self.msg_crumbs(m["crumbs"], m["busy"])
        else:
            self.msg_text(m)

    # ================= Tasten =================
    def _tab_clicked(self, _b, i):
        self.set_mode(i)
        self.text.grab_focus()

    def move(self, d):
        n = self.store.get_n_items()
        if not n:
            return
        i = max(0, min(n - 1, self.sel.get_selected() + d)) if abs(d) > 1 else (self.sel.get_selected() + d) % n
        self.sel.set_selected(i)
        self.lv.scroll_to(i, Gtk.ListScrollFlags.NONE, None)

    def switch(self, d):
        i = (self.modes.index(self.mode) + d) % len(self.modes)
        self.set_mode(i, quiet=True)

    def _key(self, _c, kv, _code, state):
        name = Gdk.keyval_name(kv) or ""
        ctrl = bool(state & Gdk.ModifierType.CONTROL_MASK)
        alt = bool(state & Gdk.ModifierType.ALT_MASK)
        shift = bool(state & Gdk.ModifierType.SHIFT_MASK)
        mod = ("ctrl+" if ctrl else "") + ("alt+" if alt else "") + name.lower() if name.isalpha() and len(name) == 1 \
            else ("ctrl+" if ctrl else "") + ("alt+" if alt else "") + name
        if self.mode.key(mod, self.query()):
            return True
        if name == "Escape":
            self.hide()
        elif name in ("Down",) or (ctrl and name in ("n", "j")):
            self.move(1)
        elif name in ("Up",) or (ctrl and name in ("p", "k")):
            self.move(-1)
        elif name == "Page_Down":
            self.move(LINES - 1)
        elif name == "Page_Up":
            self.move(-(LINES - 1))
        elif name in ("Tab", "ISO_Left_Tab"):
            self.switch(-1 if shift or name == "ISO_Left_Tab" else 1)
        elif (ctrl or alt) and name in tuple("12345678"[:len(self.modes)]):
            self.set_mode(int(name) - 1)
        elif name in ("Return", "KP_Enter"):
            self.activate(self.sel.get_selected(), alt=ctrl)
        else:
            return False
        return True

    def activate(self, pos, alt=False):
        it = self.store.get_item(pos) if pos is not None and pos < self.store.get_n_items() else None
        if it is None:
            if self.mode.id == "web" and self.query().strip():
                P.detach("xdg-open", self.mode._target(self.query())[1])
                self.hide()
            return
        if self.mode.activate(it, self.query(), alt):
            self.hide()

    # ================= Zeigen / Verstecken =================
    def focused_monitor(self):
        mons = P.hypr("j/monitors") or []
        name = next((m["name"] for m in mons if m.get("focused")), None)
        disp = Gdk.Display.get_default()
        lst = disp.get_monitors()
        for i in range(lst.get_n_items()):
            m = lst.get_item(i)
            if m.get_connector() == name:
                return m
        return None

    def _motion(self, _c, x, y):
        if self.lv.get_can_target():
            return
        if self._mouse_ref is None:
            self._mouse_ref = (x, y)
        elif abs(x - self._mouse_ref[0]) + abs(y - self._mouse_ref[1]) > 3:
            self.lv.set_can_target(True)

    def _mouse_lock(self):
        self._mouse_ref = None
        self.lv.set_can_target(False)

    def show_mode(self, name, toggle=False):
        idx = next((i for i, m in enumerate(self.modes) if m.id == name), 0 if not name else None)
        if idx is None:
            idx = 0
        visible = self.win.get_visible()
        if visible and (not name or self.modes[idx] is self.mode):
            self.hide()
            return
        if not visible:
            self._mouse_lock()
            if self.use_layer:
                mon = self.focused_monitor()
                if mon is not None:
                    Layer.set_monitor(self.win, mon)
            self.set_mode(idx)
            self.win.present()
        else:
            self.set_mode(idx)
        self.text.grab_focus()

    def _outside_click(self, gesture, _n, x, y):
        w = self.win.pick(x, y, Gtk.PickFlags.DEFAULT)
        while w is not None and w is not self.panel:
            w = w.get_parent()
        if w is None:
            self.hide()

    def hide(self):
        self.win.set_visible(False)
        self.store.remove_all()


def main():
    args = sys.argv[1:]
    app = Inquirist()
    if "--daemon" in args:
        app.daemon = True
    else:
        modes = [a for a in args if not a.startswith("-")]
        app.start_mode = modes[0] if modes else ""
    sys.exit(app.run([sys.argv[0]]))


if __name__ == "__main__":
    main()
