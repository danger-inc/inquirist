# inquirist – die Modi (Datenquellen) des Starters. Kein Fenster-Code hier: jeder Modus liefert Zeilen (Item),
# filtert sie und führt die Auswahl aus. Das Fenster (inquirist.py) zeichnet nur.
import json, os, re, shutil, socket, subprocess, threading, time, unicodedata

import gi
from gi.repository import Gio, GLib, GObject

import icons

HOME = os.path.expanduser("~")
RUN = GLib.get_user_runtime_dir()
STATE_DIR = os.path.join(GLib.get_user_state_dir(), "inquirist")
HISTORY = os.path.join(STATE_DIR, "history.json")


def esc(t):
    return GLib.markup_escape_text(t)


def dim(t):
    return f"<span alpha='55%'>{esc(t)}</span>"


# ---------------------------------------------------------------- Zeile
class Item(GObject.Object):
    """Eine Zeile der Liste. icon = Gio.Icon/Name, sonst glyph (+ css-Klasse g-…)."""

    def __init__(self, title, sub="", meta="", glyph="", css="", icon=None, main=None, extra="", ident="",
                 data=None, markup=False, selectable=True):
        super().__init__()
        self.title, self.sub, self.meta = title, sub, meta
        self.glyph, self.css, self.icon = glyph, css, icon
        self.main = (main if main is not None else title).lower()      # Treffer im Namen zählen mehr …
        self.extra = extra.lower()                                       # … als in Stichwörtern
        self.ident, self.data, self.markup, self.selectable = ident, data, markup, selectable


def fuzzy(text, tok):
    """Treffer-Güte von tok in text (höher = besser) oder None."""
    i = text.find(tok)
    if i >= 0:
        s = 100 - min(i, 40)
        if i == 0 or text[i - 1] in " -_./:":
            s += 40
        if len(text) == len(tok):
            s += 30
        return s
    p, gaps, last = 0, 0, -1
    for ch in tok:
        j = text.find(ch, p)
        if j < 0:
            return None
        if last >= 0 and j != last + 1:
            gaps += 1
        last, p = j, j + 1
    return max(5, 40 - gaps * 4 - len(text) // 8)


def score(item, toks):
    total = 0.0
    for t in toks:
        a = fuzzy(item.main, t)
        b = fuzzy(item.extra, t) if item.extra else None
        if a is None and b is None:
            return None
        total += max(a if a is not None else -1, (b * 0.5) if b is not None else -1)
    return total - len(item.main) * 0.02


def filter_items(items, q, limit=400):
    toks = q.lower().split()
    if not toks:
        return items[:limit] if limit else items
    hits = []
    for n, it in enumerate(items):
        s = score(it, toks)
        if s is not None:
            hits.append((-s, n, it))
    hits.sort(key=lambda h: (h[0], h[1]))
    return [h[2] for h in hits[:limit]]


# ---------------------------------------------------------------- Häufigkeit
class History:
    def __init__(self):
        try:
            self.d = json.load(open(HISTORY))
        except (OSError, ValueError):
            self.d = {}

    def bump(self, mode, ident):
        if not ident:
            return
        c, _ = self.d.get(f"{mode}:{ident}", [0, 0])
        self.d[f"{mode}:{ident}"] = [c + 1, time.time()]
        try:
            os.makedirs(STATE_DIR, exist_ok=True)
            json.dump(self.d, open(HISTORY + ".tmp", "w"))
            os.replace(HISTORY + ".tmp", HISTORY)
        except OSError:
            pass

    def weight(self, mode, ident):
        c, t = self.d.get(f"{mode}:{ident}", [0, 0])
        if not c:
            return 0.0
        return c / (1.0 + (time.time() - t) / 86400.0 / 14.0)


# ---------------------------------------------------------------- Hilfen
def sh(*cmd, timeout=3, inp=None):
    try:
        return subprocess.run(list(cmd), capture_output=True, text=True, timeout=timeout, input=inp).stdout
    except Exception:
        return ""


def detach(*cmd, stdin=None):
    """Programm unabhängig von uns starten."""
    try:
        p = subprocess.Popen(list(cmd), stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        if stdin is not None:
            p.stdin.write(stdin if isinstance(stdin, bytes) else stdin.encode())
            p.stdin.close()
    except OSError:
        pass


def notify(text):
    detach("notify-send", "-a", "inquirist", "-t", "1500", text)


def copy(text, what=None):
    detach("wl-copy", stdin=text)
    notify(f"{what or text[:60]} kopiert")


def hypr(cmd):
    """Anfrage an den Hyprland-Socket (z. B. "j/clients") → JSON oder None."""
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not sig:
        return None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(f"{RUN}/hypr/{sig}/.socket.sock")
            s.sendall(cmd.encode())
            data = b""
            while chunk := s.recv(65536):
                data += chunk
        return json.loads(data)
    except (OSError, ValueError):
        return None


def terminal_cmd():
    """Terminal samt „führe aus“-Schalter (das erste, das es gibt)."""
    for t, flag in (("kitty", "-e"), ("foot", "-e"), ("alacritty", "-e"), ("wezterm", "start"), ("konsole", "-e"),
                    ("gnome-terminal", "--"), ("xfce4-terminal", "-x"), ("xterm", "-e")):
        if shutil.which(t):
            return [t, flag]
    return ["xterm", "-e"]


class Mode:
    """Grundlage der Modi. Die Fenster-Schicht (ui) bietet refilter(), say(text), close()."""
    id = ""
    label = ""
    hint = "enter öffnen"
    placeholder = "suchen …"

    def __init__(self, ui):
        self.ui = ui
        self.items = []

    def show(self):
        """Fenster geht auf (bzw. Modus wird gewählt): Daten sofort aus dem Zwischenspeicher, dann frisch."""

    def rows(self, q):
        return filter_items(self.items, q)

    def total(self):
        return len(self.items)

    def busy(self, q):
        """Es kommen noch Zeilen nach (dann kein „keine treffer“)."""
        return False

    def message(self, q):
        return ""

    def activate(self, item, q, alt=False):
        """→ True = Fenster schließen."""
        return True

    def key(self, name, q):
        """Sondertasten des Modus; → True = behandelt."""
        return False


# ---------------------------------------------------------------- apps
class Apps(Mode):
    id, label = "apps", "apps"
    hint = "enter starten"
    placeholder = "programm suchen …"

    def __init__(self, ui):
        super().__init__(ui)
        self.mon = Gio.AppInfoMonitor.get()
        self.dirty = True
        self.mon.connect("changed", lambda *_: setattr(self, "dirty", True))
        self.by_id = {}

    def show(self):
        if not self.dirty and self.items:
            self._order()
            return
        self.dirty = False
        items = []
        for info in Gio.AppInfo.get_all():
            if not info.should_show():
                continue
            name = info.get_display_name() or info.get_name()
            gen = keys = cats = ""
            if isinstance(info, Gio.DesktopAppInfo):
                gen = info.get_generic_name() or ""
                keys = " ".join(info.get_keywords() or [])
                cats = (info.get_categories() or "").replace(";", " ")
            exe = (info.get_executable() or "")
            it = Item(esc(name), dim(gen) if gen else "", icon=info.get_icon() or Gio.ThemedIcon.new("application-x-executable"), main=name,
                      extra=f"{gen} {exe} {keys} {cats}", ident=info.get_id() or name, data=info, markup=True)
            items.append(it)
        items.sort(key=lambda i: i.main)
        self.base = items
        self._order()

    def _order(self):
        h = self.ui.history
        self.items = sorted(self.base, key=lambda i: -h.weight("apps", i.ident))

    def activate(self, item, q, alt=False):
        info = item.data
        self.ui.history.bump("apps", item.ident)
        if isinstance(info, Gio.DesktopAppInfo) and info.get_boolean("Terminal"):
            cmd = re.sub(r"%[a-zA-Z%]", "", info.get_commandline() or "").strip()
            detach(*terminal_cmd(), "sh", "-c", cmd)
            return True
        try:
            ctx = self.ui.launch_context()
            info.launch([], ctx)
        except GLib.Error as e:
            self.ui.say(f"starten fehlgeschlagen: {e.message}")
            return False
        return True


# ---------------------------------------------------------------- fenster
class Windows(Mode):
    id, label = "fenster", "fenster"
    hint = "enter hinspringen   strg+x schließen"
    placeholder = "fenster suchen …"

    def __init__(self, ui):
        super().__init__(ui)
        self.icon_map = None

    def _icons(self):
        if self.icon_map is None:
            m = {}
            for info in Gio.AppInfo.get_all():
                if not isinstance(info, Gio.DesktopAppInfo):
                    continue
                ic = info.get_icon()
                if not ic:
                    continue
                did = (info.get_id() or "")[:-8].lower()
                for k in (info.get_startup_wm_class(), did, did.split(".")[-1]):
                    if k:
                        m.setdefault(k.lower(), ic)
            self.icon_map = m
        return self.icon_map

    def message(self, q):
        return "" if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") else dim("die fensterliste gibt es nur unter hyprland")

    def show(self):
        clients = hypr("j/clients") or []
        active = (hypr("j/activewindow") or {}).get("address")
        ics = self._icons()
        shown = [c for c in clients if c.get("mapped") and c.get("title") is not None]
        shown.sort(key=lambda c: c.get("focusHistoryID", 99))
        items = []
        multi = len({c.get("monitor") for c in shown}) > 1
        for c in shown:
            cls = c.get("class") or c.get("initialClass") or "?"
            ws = str(c.get("workspace", {}).get("name", "?"))
            ws = "spezial" if ws.startswith("special") else ws
            where = f"fläche {ws}" + (f" · bildschirm {c.get('monitor')}" if multi else "")
            tag = "aktuell · " if c["address"] == active else ""
            ic = ics.get(cls.lower()) or ics.get(cls.lower().split(".")[-1])
            title = c.get("title") or cls
            it = Item(esc(title[:80]), dim(f"{tag}{cls.split('.')[-1].lower()} · {where}"), icon=ic,
                      glyph="" if ic else "\U000F05B2", main=title, extra=f"{cls} {ws}",
                      ident=c["address"], data=c, markup=True)
            items.append(it)
        # das Fenster, aus dem man kommt, ans Ende: Enter springt zuerst zum vorherigen
        items.sort(key=lambda i: i.ident == active)
        self.items = items

    def activate(self, item, q, alt=False):
        detach("hyprctl", "dispatch", f'hl.dsp.focus({{ window = "address:{item.ident}" }})')
        return True

    def key(self, name, q):
        if name == "ctrl+x":
            row = self.ui.current()
            if row is not None:
                detach("hyprctl", "dispatch", f'hl.dsp.window.close({{ window = "address:{row.ident}" }})')
                self.items = [i for i in self.items if i is not row]
                self.ui.refilter()
            return True
        return False


# ---------------------------------------------------------------- dateien (im Look von filist)
def human_size(n):
    if n is None:
        return ""
    if n < 1000:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB", "PB"):
        n /= 1000
        if n < 1000 or unit == "PB":
            s = f"{n:.1f}" if n < 100 else f"{n:.0f}"
            return s.replace(".", ",") + " " + unit
    return ""


def human_date(ts):
    import datetime
    if not ts:
        return ""
    d = datetime.datetime.fromtimestamp(ts)
    now = datetime.datetime.now()
    if d.date() == now.date():
        return f"heute {d:%H:%M}"
    if (now.date() - d.date()).days == 1:
        return f"gestern {d:%H:%M}"
    if d.year == now.year:
        return f"{d:%d.%m. %H:%M}"
    return f"{d:%d.%m.%Y}"


def natural_key(name):
    return [(0, int(p)) if p.isdigit() else (1, p) for p in re.split(r"(\d+)", name.casefold()) if p]


SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".cache", "venv", ".venv", "site-packages", ".cargo", ".npm",
             ".mozilla", ".steam", "Trash", ".wine"}


class Files(Mode):
    id, label = "dateien", "dateien"
    hint = "enter öffnen   strg+⏎ in filist   ⌫ ordner hoch   strg+h versteckte"
    placeholder = "datei oder ordner …  (/ oder ~/ tippt einen pfad)"

    def __init__(self, ui):
        super().__init__(ui)
        self.cwd = HOME
        self.entries = []
        self.cache = {}
        self.hidden = False
        self.gen = 0
        self.loading = False
        self.found = []                   # Treffer der Tiefensuche (unterhalb von cwd)
        self.found_for = None
        self._search_timer = 0
        self._search_gen = 0
        self.bak = {}

    def show(self):
        self.go(HOME)

    # ---- Ordner lesen
    def go(self, path):
        path = os.path.normpath(path) or "/"
        self.cwd = path
        self.found, self.found_for = [], None
        self.gen += 1
        gen = self.gen
        hit = self.cache.get(path)
        if hit and time.time() - hit[0] < 30:
            self.entries = hit[1]
            self.loading = False
            return
        self.entries = hit[1] if hit else []
        self.loading = True

        def work():
            items, err = self._scan(path)
            GLib.idle_add(self._loaded, gen, path, items, err)
        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, gen, path, items, err):
        if gen != self.gen:
            return False
        self.loading = False
        self.entries = items
        if not err:
            self.cache[path] = (time.time(), items)
            if len(self.cache) > 12:
                self.cache.pop(next(iter(self.cache)))
        else:
            self.ui.say(err)
        self.ui.refilter()
        return False

    def _scan(self, path):
        out = []
        try:
            with os.scandir(path) as it:
                for e in it:
                    try:
                        out.append(self._item(e.name, e.path, e.is_dir(), e.is_symlink(), e.stat(follow_symlinks=False)))
                    except OSError:
                        out.append(self._item(e.name, e.path, False, False, None))
        except OSError as ex:
            return [], f"{path}: {ex.strerror}"
        out.sort(key=lambda i: (not i.data["dir"], natural_key(i.main)))
        return out, None

    def _item(self, name, path, is_dir, is_link, st, sub=""):
        ex = bool(st and not is_dir and st.st_mode & 0o111)
        glyph, group = icons.for_name(name, is_dir, is_link, ex)
        size = None if is_dir else (st.st_size if st else None)
        meta = f"{human_size(size):>9}   {human_date(st.st_mtime if st else 0):<13}"
        it = Item(esc(name), dim(sub) if sub else "", meta=meta, glyph=glyph,
                  css=f"g-{group}" + (" flink" if is_link else "") + (" fhidden" if name.startswith(".") else ""),
                  main=name, ident=path, data={"dir": is_dir, "path": path}, markup=True)
        return it

    # ---- Eingabe → Ordner + Filter
    def _split(self, q):
        if q.startswith(("/", "~")):
            d, _, base = q.rpartition("/")
            if q == "~":
                return HOME, ""
            path = os.path.expanduser(d if d else "/")
            if os.path.isdir(path):
                return path, base
        return None, q

    def rows(self, q):
        path, filt = self._split(q)
        if path is not None and os.path.normpath(path) != self.cwd:
            self.go(path)
        toks = filt.lower().split()
        show_hidden = self.hidden or filt.startswith(".")
        pool = [i for i in self.entries if show_hidden or not i.main.startswith(".")]
        if toks:
            hits = []
            for n, it in enumerate(pool):
                s = score(it, toks)
                if s is not None:
                    hits.append((-s, not it.data["dir"], n, it))
            hits.sort(key=lambda h: h[:3])
            pool = [h[3] for h in hits]
        rows = pool
        if len(filt.strip()) >= 2 and not filt.startswith("."):
            self._schedule_search(filt)
            if self.found_for == (self.cwd, filt):
                have = {r.ident for r in rows}
                rows = rows + [f for f in self.found if f.ident not in have]
        else:
            self._search_gen += 1
        return rows

    def total(self):
        return len(self.entries)

    # ---- Tiefensuche unterhalb des Ordners (verzögert, bricht bei neuer Eingabe ab)
    def _schedule_search(self, filt):
        if self.found_for == (self.cwd, filt):
            return
        if self._search_timer:
            GLib.source_remove(self._search_timer)
        self._search_gen += 1
        gen, root = self._search_gen, self.cwd
        self._search_timer = GLib.timeout_add(220, self._start_search, gen, root, filt)

    def _start_search(self, gen, root, filt):
        self._search_timer = 0
        toks = filt.lower().split()

        def work():
            res, t0, n = [], time.time(), 0
            for dirpath, dirs, files in os.walk(root):
                if gen != self._search_gen or time.time() - t0 > 1.6 or len(res) >= 120:
                    break
                depth = dirpath[len(root):].count("/")
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS] if depth < 6 else []
                for name in dirs + files:
                    n += 1
                    low = name.lower()
                    if all(t in low for t in toks):
                        p = os.path.join(dirpath, name)
                        try:
                            st = os.lstat(p)
                        except OSError:
                            continue
                        rel = os.path.relpath(dirpath, root)
                        res.append(self._item(name, p, os.path.isdir(p), os.path.islink(p), st,
                                              sub="" if rel == "." else rel))
                        if len(res) >= 120:
                            break
            GLib.idle_add(self._found, gen, root, filt, res)
        threading.Thread(target=work, daemon=True).start()
        return False

    def _found(self, gen, root, filt, res):
        if gen != self._search_gen or root != self.cwd:
            return False
        self.found, self.found_for = res, (root, filt)
        self.ui.refilter(keep=True)
        return False

    def busy(self, q):
        _, filt = self._split(q)
        return self.loading or (len(filt.strip()) >= 2 and self.found_for != (self.cwd, filt))

    # ---- Anzeige
    def message(self, q):
        path, _ = self._split(q)
        base = self.cwd
        parts = []
        if base == HOME or base.startswith(HOME + "/"):
            parts.append(("\U000F02DC", HOME))
            rest = base[len(HOME):].strip("/")
        else:
            parts.append(("\U000F0A0A", "/"))
            rest = base.strip("/")
        cur = parts[0][1]
        for seg in [s for s in rest.split("/") if s]:
            cur = os.path.join(cur, seg)
            parts.append((seg, cur))
        return {"crumbs": parts, "busy": self.loading}

    def activate(self, item, q, alt=False):
        d = item.data
        if alt:
            fl = shutil.which("filist")
            detach(fl, d["path"]) if fl else detach("xdg-open", d["path"] if d["dir"] else os.path.dirname(d["path"]))
            return True
        if d["dir"]:
            self.ui.set_query("")
            self.go(d["path"])
            self.ui.refilter()
            return False
        detach("xdg-open", d["path"])
        return True

    def navigate(self, path):
        self.ui.set_query("")
        self.go(path)
        self.ui.refilter()

    def key(self, name, q):
        if name == "BackSpace" and not q or name == "alt+Up" or name == "alt+Left":
            parent = os.path.dirname(self.cwd)
            if parent and parent != self.cwd:
                self.navigate(parent)
            return True
        if name == "ctrl+h":
            self.hidden = not self.hidden
            self.ui.say("versteckte dateien " + ("an" if self.hidden else "aus"))
            self.ui.refilter()
            return True
        return False


# ---------------------------------------------------------------- rechner
def calc_expr(expr):
    q = re.sub(r"%\s*(von|of)\s+", "% * ", expr)
    q = re.sub(r"\s(in|nach|zu)\s(?=[^\d\s])", " to ", q)
    q = re.sub(r"\bto\s+(?!-|\+|dec\b|hex\b|bin\b|oct\b|base|roman|time\b|frac|mixed|sci|utc|cet)([A-Za-z€$£]\w*)",
               r"to -\1", q)
    q = re.sub(r"\bmal\b", "*", q)
    q = re.sub(r"\bgeteilt durch\b", "/", q)
    res = sh("qalc", "-t", "-set", "decimal comma on", q, timeout=8).strip().splitlines()
    return res[-1].strip() if res else "?"


DIVIST = shutil.which("divist") or os.path.join(HOME, ".local/bin/divist")


class Calc(Mode):
    id, label = "rechner", "rechner"
    hint = "enter kopiert   strg+⏎ ergebnis anhängen   unten: in divist öffnen"
    placeholder = "12% von 80 · 5 km in mi · sqrt(2) · 100 eur in usd …   (gleichungen, ableitungen … → divist)"
    FILE = os.path.join(RUN, "inquirist-rechner.json")

    def __init__(self, ui):
        super().__init__(ui)
        self.cur = None            # (ausdruck, ergebnis)
        self.pending = 0
        self.gen = 0
        try:
            self.hist = json.load(open(self.FILE))
        except (OSError, ValueError):
            self.hist = []

    def show(self):
        self.cur = None

    def busy(self, q):
        return bool(q.strip()) and not (self.cur and self.cur[0] == q.strip())

    def rows(self, q):
        out = []
        q = q.strip()
        if q:
            if self.pending:
                GLib.source_remove(self.pending)
            self.gen += 1
            if self.cur and self.cur[0] == q:
                pass
            else:
                self.pending = GLib.timeout_add(140, self._run, q, self.gen)
            if self.cur and self.cur[0] == q:
                out.append(Item(f"<b>{esc(self.cur[1])}</b>", dim("= " + q), glyph="\U000F00E8", css="g-code",
                                ident=self.cur[1], data=("res", self.cur[1]), markup=True))
            if os.path.exists(DIVIST):
                out.append(Item("in divist öffnen", dim(q), glyph="\U000F00EC", css="g-code", main="divist " + q,
                                ident="divist:" + q, data=("divist", q)))
        elif os.path.exists(DIVIST):
            out.append(Item("divist", dim("Taschenrechner mit Brüchen, Gleichungen, Graph …"), glyph="\U000F00EC",
                            css="g-code", main="divist rechner", ident="divist:", data=("divist", "")))
        for expr, res in self.hist:
            out.append(Item(f"<b>{esc(res)}</b>", dim("= " + expr), glyph="\U000F02DA", css="g-file",
                            ident=res, data=("hist", expr), main=expr, markup=True))
        return out

    def total(self):
        return len(self.hist)

    def message(self, q):
        if q.strip():
            return ""
        return dim("ausdruck tippen – das ergebnis erscheint sofort · einheiten, prozent, währungen")

    def _run(self, q, gen):
        self.pending = 0

        def work():
            res = calc_expr(q)
            GLib.idle_add(self._done, q, res, gen)
        threading.Thread(target=work, daemon=True).start()
        return False

    def _done(self, q, res, gen):
        if gen != self.gen:
            return False
        self.cur = (q, res)
        self.ui.refilter(keep=False)
        return False

    def activate(self, item, q, alt=False):
        kind, val = item.data
        res = item.ident
        if kind == "divist":
            detach(DIVIST, val) if val else detach(DIVIST)
            return True
        if kind == "res":
            self.hist = [[q.strip(), res]] + [h for h in self.hist if h[0] != q.strip()][:14]
            try:
                json.dump(self.hist, open(self.FILE, "w"))
            except OSError:
                pass
        if alt:
            self.ui.set_query(res)
            return False
        copy(res, f"Ergebnis {res}")
        return True


# ---------------------------------------------------------------- ablage
class Clip(Mode):
    id, label = "ablage", "ablage"
    hint = "enter kopiert erneut"
    placeholder = "zwischenablage durchsuchen …"

    def show(self):
        def work():
            lines = sh("cliphist", "list", timeout=4).splitlines()
            GLib.idle_add(self._set, lines)
        threading.Thread(target=work, daemon=True).start()

    loaded = False

    def busy(self, q):
        return not self.loaded

    def _set(self, lines):
        self.loaded = True
        items = []
        for line in lines[:300]:
            cid, _, prev = line.partition("\t")
            if prev.startswith("[[ binary data"):
                it = Item(dim("bild " + prev.strip("[] ").replace("binary data", "").strip()), glyph="\U000F021F",
                          css="g-img", main="bild image", ident=line, markup=True)
            else:
                p = " ".join(prev.split())
                it = Item(esc(p[:110]) + ("…" if len(p) > 110 else ""), glyph="\U000F0219", css="g-txt",
                          main=prev[:300], ident=line, markup=True)
            items.append(it)
        if items:
            items.append(Item(dim("verlauf leeren"), glyph="\U000F0A79", css="g-link", main="leeren löschen wipe clear",
                              ident="__wipe__", markup=True))
        self.items = items
        self.empty = not items
        self.ui.refilter(keep=True)

    def message(self, q):
        return dim("verlauf ist leer") if getattr(self, "empty", False) else ""

    def activate(self, item, q, alt=False):
        if item.ident == "__wipe__":
            sh("cliphist", "wipe")
            notify("Verlauf geleert")
            return True
        data = subprocess.run(["cliphist", "decode"], input=item.ident.encode() + b"\n", capture_output=True).stdout
        detach("wl-copy", stdin=data)
        notify("Wieder in der Zwischenablage")
        return True


# ---------------------------------------------------------------- zeichen
DE = {
    "😀": "lachen grinsen", "😂": "tränen lachen", "😊": "lächeln", "😍": "verliebt herzaugen", "🤔": "nachdenken",
    "😢": "weinen traurig", "😭": "heulen", "😡": "wütend", "😴": "schlafen müde", "🙏": "bitte danke beten",
    "👍": "daumen hoch gut", "👎": "daumen runter schlecht", "👏": "klatschen applaus", "🙌": "hurra", "💪": "stark muskel",
    "❤": "herz liebe", "🔥": "feuer heiß", "✨": "funkeln glitzer", "🎉": "party feier", "✅": "haken erledigt ok",
    "❌": "kreuz falsch nein", "⚠": "warnung achtung", "💡": "idee glühbirne", "📌": "pin anheften", "📎": "büroklammer",
    "🚀": "rakete start", "⭐": "stern", "☕": "kaffee", "🍕": "pizza", "🍺": "bier", "🎂": "geburtstag kuchen",
    "📅": "kalender datum", "⏰": "wecker", "📧": "email mail", "📞": "telefon", "🏠": "haus zuhause", "🚗": "auto",
    "🎵": "musik note", "📷": "kamera foto", "💻": "laptop computer", "📱": "handy", "🔒": "schloss gesperrt",
    "🔑": "schlüssel", "💀": "totenkopf schädel", "👀": "augen gucken", "🤷": "schulterzucken egal", "😅": "puh schwitzen",
    "🥲": "lächeln träne", "🫠": "schmelzen", "🤝": "handschlag deal", "👋": "winken hallo tschüss", "🐱": "katze",
    "🐶": "hund", "🌙": "mond nacht", "☀": "sonne", "🌧": "regen", "❄": "schnee kalt", "⚡": "blitz strom",
}
SYMBOLS = [
    ("→", "pfeil rechts arrow"), ("←", "pfeil links"), ("↑", "pfeil hoch"), ("↓", "pfeil runter"), ("↔", "pfeil beide"),
    ("⇒", "folgt daraus implies"), ("⇔", "äquivalent"), ("✓", "haken check"), ("✗", "kreuz"), ("•", "punkt bullet"),
    ("…", "auslassung ellipsis"), ("–", "halbgeviertstrich en dash"), ("—", "geviertstrich em dash"),
    ("„", "anführung unten"), ("“", "anführung oben"), ("‚", "einfach unten"), ("‘", "einfach oben"),
    ("»", "guillemet"), ("«", "guillemet"), ("°", "grad degree"), ("€", "euro"), ("£", "pfund"), ("$", "dollar"),
    ("¥", "yen"), ("±", "plusminus"), ("×", "mal times"), ("÷", "geteilt divide"), ("·", "malpunkt"),
    ("≈", "ungefähr approx"), ("≠", "ungleich"), ("≤", "kleiner gleich"), ("≥", "größer gleich"), ("∞", "unendlich"),
    ("√", "wurzel"), ("∑", "summe sigma"), ("∏", "produkt"), ("∫", "integral"), ("∂", "partiell"), ("∆", "delta"),
    ("∇", "nabla"), ("∈", "element"), ("∉", "nicht element"), ("⊂", "teilmenge"), ("∪", "vereinigung"),
    ("∩", "schnitt"), ("∀", "für alle"), ("∃", "existiert"), ("¬", "nicht"), ("∧", "und"), ("∨", "oder"),
    ("α", "alpha"), ("β", "beta"), ("γ", "gamma"), ("δ", "delta klein"), ("ε", "epsilon"), ("λ", "lambda"),
    ("μ", "my mikro"), ("π", "pi"), ("ρ", "rho"), ("σ", "sigma klein"), ("τ", "tau"), ("φ", "phi"), ("ω", "omega klein"),
    ("Ω", "omega ohm"), ("²", "hoch zwei quadrat"), ("³", "hoch drei"), ("½", "halb"), ("¼", "viertel"),
    ("¾", "dreiviertel"), ("‰", "promille"), ("§", "paragraph"), ("©", "copyright"), ("®", "registered"),
    ("™", "trademark"), ("†", "kreuz gestorben"), ("ß", "eszett"), ("ẞ", "großes eszett"), ("⌘", "command"),
    ("⌥", "option alt"), ("⇧", "umschalt shift"), ("⏎", "enter"), ("⌫", "rücktaste backspace"), ("␣", "leerzeichen"),
]


class Chars(Mode):
    id, label = "zeichen", "zeichen"
    hint = "enter kopiert"
    placeholder = "emoji oder sonderzeichen …  (deutsch und englisch)"

    def show(self):
        if self.items:
            return
        cache = os.path.join(GLib.get_user_cache_dir(), "inquirist-zeichen.tsv")
        if os.path.exists(cache):
            lines = open(cache).read().splitlines()
        else:
            lines = [f"{ch}\t{unicodedata.name(ch, '').lower()}\t{kw}" for ch, kw in SYMBOLS]
            for a, b in [(0x1F600, 0x1F64F), (0x1F910, 0x1F9FF), (0x1F300, 0x1F5FF), (0x1F680, 0x1F6FF),
                         (0x1FA70, 0x1FAFF), (0x2600, 0x27BF)]:
                for cp in range(a, b + 1):
                    ch = chr(cp)
                    name = unicodedata.name(ch, "")
                    if name and unicodedata.category(ch) in ("So", "Sm"):
                        lines.append(f"{ch}\t{name.lower()}\t{DE.get(ch, '')}")
            try:
                open(cache, "w").write("\n".join(lines))
            except OSError:
                pass
        for line in lines:
            ch, name, kw = (line.split("\t") + ["", ""])[:3]
            self.items.append(Item(esc(name), glyph=ch, css="char", main=name, extra=kw, ident=ch, markup=True))

    def activate(self, item, q, alt=False):
        copy(item.ident)
        return True


# ---------------------------------------------------------------- web
ENGINES = {
    "": ("DuckDuckGo", "https://duckduckgo.com/?q={}"),
    "g": ("Google", "https://www.google.com/search?q={}"),
    "yt": ("YouTube", "https://www.youtube.com/results?search_query={}"),
    "w": ("Wikipedia", "https://de.wikipedia.org/w/index.php?search={}"),
    "gh": ("GitHub", "https://github.com/search?q={}&type=repositories"),
    "aw": ("Arch Wiki", "https://wiki.archlinux.org/index.php?search={}"),
    "aur": ("AUR", "https://aur.archlinux.org/packages?K={}"),
    "maps": ("Google Maps", "https://www.google.com/maps/search/{}"),
    "dict": ("dict.cc", "https://www.dict.cc/?s={}"),
}


class Web(Mode):
    id, label = "web", "web"
    hint = "enter sucht   kürzel + leerzeichen wählt die seite"
    placeholder = "suchbegriff oder adresse …  (g, yt, w, gh, aw, aur, maps, dict)"

    def _target(self, q):
        from urllib.parse import quote_plus
        q = q.strip()
        if q.startswith(("http://", "https://")) or ("." in q and " " not in q and len(q.split(".")[-1]) in (2, 3, 4)
                                                       and not q.startswith("/")):
            return ("adresse öffnen", q if "://" in q else "https://" + q)
        key, _, rest = q.partition(" ")
        if key in ENGINES and key and rest.strip():
            n, u = ENGINES[key]
            return (n, u.format(quote_plus(rest.strip())))
        n, u = ENGINES[""]
        return (n, u.format(quote_plus(q)))

    def rows(self, q):
        out = []
        if q.strip():
            name, url = self._target(q)
            out.append(Item(f"{esc(q.strip())}  " + dim(name), glyph="\U000F0349", css="g-code", ident=url,
                            data=url, markup=True))
        for key, (name, _u) in ENGINES.items():
            if key:
                out.append(Item(f"<b>{key}</b> …  {dim(name)}", glyph="\U000F059F", css="g-file", ident=key,
                                data="key", markup=True))
        return out

    def total(self):
        return len(ENGINES) - 1

    def message(self, q):
        return "" if q.strip() else dim("suchbegriff + enter sucht mit duckduckgo · kürzel davor wählt die seite")

    def activate(self, item, q, alt=False):
        if item.data == "key":
            self.ui.set_query(item.ident + " ")
            return False
        detach("xdg-open", item.data)
        return True


# ---------------------------------------------------------------- system
class System(Mode):
    id, label = "system", "system"
    hint = "enter ausführen"
    placeholder = "sperren, wlan, bluetooth, screenshot, … "

    ACTIONS = {
        "lock": ["bash", "-c", "if command -v hyprlock >/dev/null; then awww query 2>/dev/null | awk -F 'image: ' '{print $2}' | xargs -I {} cp {} ~/.cache/current_wallpaper.png; hyprlock; else loginctl lock-session; fi"],
        "suspend": ["systemctl", "suspend"],
        "logout": ["bash", "-c", "if [ -n \"$HYPRLAND_INSTANCE_SIGNATURE\" ]; then hyprctl dispatch 'hl.dsp.exit()'; else loginctl terminate-user \"$USER\"; fi"],
        "reboot": ["systemctl", "reboot"],
        "poweroff": ["systemctl", "poweroff"],
        "wifi": ["bash", "-c", "[ \"$(nmcli radio wifi)\" = enabled ] && nmcli radio wifi off || nmcli radio wifi on"],
        "bt": ["bash", "-c", "bluetoothctl show | grep -q 'Powered: yes' && bluetoothctl power off || bluetoothctl power on"],
        "dnd": ["swaync-client", "-d", "-sw"],
        "wall": [os.path.join(HOME, ".config/hypr/random_wall.sh")],
        "waybar": [os.path.join(HOME, ".config/waybar/scripts/style-switch.sh")],
        "shot": ["hyprshot", "-m", "region"],
        "shotwin": ["hyprshot", "-m", "window"],
        "pick": ["hyprpicker", "-a", "-n"],
        "night": ["bash", "-c", "pkill -x hyprsunset || hyprsunset -t 4500"],
    }
    CONFIRM = {"reboot": "neu starten", "poweroff": "ausschalten", "logout": "abmelden"}

    def __init__(self, ui):
        super().__init__(ui)
        self.states = {}
        self.confirm = None

    def show(self):
        self.confirm = None
        self._build()

        def work():
            def st(cmd, words):
                return any(w in sh(*cmd).lower() for w in words)
            s = {"wifi": st(["nmcli", "radio", "wifi"], ["enabled"]), "bt": st(["bluetoothctl", "show"], ["powered: yes"]),
                 "dnd": sh("swaync-client", "-D").strip() == "true"}
            GLib.idle_add(self._states, s)
        threading.Thread(target=work, daemon=True).start()

    def _states(self, s):
        self.states = s
        self._build()
        self.ui.refilter(keep=True)
        return False

    def _build(self):
        on = lambda k: "<b>an</b>" if self.states.get(k) else dim("aus") if k in self.states else ""
        has_sun = bool(sh("which", "hyprsunset").strip())
        rows = [
            ("󰌾", "sperren", dim("super+l"), "lock", "lock sperren bildschirm"),
            ("󰤄", "bereitschaft", dim("suspend"), "suspend", "schlafen suspend standby"),
            ("󰍃", "abmelden", dim("hyprland beenden"), "logout", "logout abmelden"),
            ("󰜉", "neu starten", "", "reboot", "reboot restart neustart"),
            ("󰐥", "ausschalten", "", "poweroff", "shutdown poweroff herunterfahren aus"),
            ("󰖩", "wlan", on("wifi"), "wifi", "wifi wlan netz"),
            ("󰂯", "bluetooth", on("bt"), "bt", "bluetooth bt"),
            ("󰂛", "nicht stören", on("dnd"), "dnd", "dnd nicht stören benachrichtigungen"),
            ("󰸉", "neues wallpaper", dim("super+w · farben passen sich an"), "wall", "wallpaper hintergrund farben"),
            ("󰕮", "waybar-look wechseln", dim("kopfzeile → reiter → klassisch"), "waybar", "waybar leiste look"),
            ("󰹑", "screenshot bereich", dim("super+print"), "shot", "screenshot bildschirmfoto"),
            ("󰖯", "screenshot fenster", dim("super+shift+print"), "shotwin", "screenshot fenster"),
            ("󰈊", "farbe vom bildschirm", dim("pipette · hex wird kopiert"), "pick", "farbe pipette color picker"),
            ("󰖔", "nachtlicht", dim("warmes licht an/aus"), "night", "nachtlicht night blaulicht"),
        ]
        def usable(key):                 # nur anbieten, was es auf diesem System gibt
            cmd = self.ACTIONS[key]
            if key == "night":
                return has_sun
            if key == "dnd":
                return bool(shutil.which("swaync-client"))
            if key in ("shot", "shotwin"):
                return bool(shutil.which("hyprshot"))
            if key == "pick":
                return bool(shutil.which("hyprpicker"))
            if key == "wifi":
                return bool(shutil.which("nmcli"))
            if key == "bt":
                return bool(shutil.which("bluetoothctl"))
            if cmd[0].startswith("/"):
                return os.path.exists(cmd[0])
            return bool(shutil.which(cmd[0]))
        rows = [r for r in rows if usable(r[3])]
        self.base = [Item(f"{esc(name)}", extra, glyph=ic, css="g-code", main=name, extra=meta, ident=key, markup=True)
                     for ic, name, extra, key, meta in rows]
        self.base += self._design_rows()
        self.items = self.base

    def _design_rows(self):
        """Design der ganzen Suite (~/.config/ist-theme.json) – wirkt live in allen offenen Apps."""
        try:
            import istheme
        except ImportError:
            return []
        st = istheme.load()
        cur = lambda on: "<b>an</b>" if on else ""
        auto = st["theme"] == "auto"
        out = [Item("design: automatisch · dunkel", cur(auto and st["mode"] == "dark"), glyph="󰏘", css="g-code",
                    main="design automatisch dunkel", extra="theme farben matugen darkmode", ident="theme:auto:dark",
                    markup=True),
               Item("design: automatisch · hell", cur(auto and st["mode"] == "light"), glyph="󰏘", css="g-code",
                    main="design automatisch hell", extra="theme farben matugen lightmode", ident="theme:auto:light",
                    markup=True)]
        for key, t in istheme.THEMES.items():
            out.append(Item(f"design: {esc(t[0].lower())}", cur(st["theme"] == key), glyph="󰏘", css="g-code",
                            main="design " + t[0].lower(), extra="theme farben " + ("hell" if t[1] else "dunkel"),
                            ident="theme:" + key, markup=True))
        return out

    def rows(self, q):
        if self.confirm:
            return [Item(f"ja, {self.CONFIRM[self.confirm]}", glyph="\U000F012C", css="g-code", ident="yes",
                         markup=True),
                    Item("abbrechen", glyph="\U000F0739", css="g-link", ident="back", markup=True)]
        return filter_items(self.items, q)

    def message(self, q):
        if self.confirm:
            return f"wirklich <b>{self.CONFIRM[self.confirm]}</b>? offene programme werden beendet."
        return ""

    def activate(self, item, q, alt=False):
        k = item.ident
        if self.confirm:
            act, self.confirm = self.confirm, None
            if k == "yes":
                detach(*self.ACTIONS[act])
                return True
            self.ui.set_query("")
            self.ui.refilter()
            return False
        if k.startswith("theme:"):
            import istheme
            _t, key, *mode = k.split(":")
            istheme.save(theme=key, mode=mode[0] if mode else None)
            self._build()
            self.ui.refilter(keep=True)
            return False
        if k in self.CONFIRM:
            self.confirm = k
            self.ui.set_query("")
            self.ui.refilter()
            return False
        detach(*self.ACTIONS[k])
        return True


MODES = [Apps, Windows, Files, Calc, Clip, Chars, Web, System]
