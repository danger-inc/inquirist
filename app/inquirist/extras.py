# inquirist – weitere Modi: notizen (notist), mails (mailist), termine (datist), links (Browser-Lesezeichen),
# befehle (eigene Befehle + Textbausteine) und Plugin-Modi (eigene Skripte). Alles nur lesend; geöffnet wird in der
# jeweiligen App. Einstellungen: ~/.config/inquirist/config.json (siehe CONFIG_HELP).
import datetime, glob, json, os, re, shlex, shutil, sqlite3, subprocess, tempfile, threading, time

from gi.repository import GLib

from providers import Item, Mode, HOME, copy, detach, dim, esc, filter_items, human_date, notify, score, sh, terminal_cmd

CONF = os.path.join(GLib.get_user_config_dir(), "inquirist", "config.json")

CONFIG_HELP = (
    '{"commands":[{"name":"vpn an","cmd":"nmcli con up uni","terminal":false,"keywords":"netzwerk"}], '
    '"snippets":[{"name":"meine adresse","text":"Musterstraße 1"}], '
    '"engines":{"r":["Reddit","https://www.reddit.com/search/?q={}"]}, '
    '"plugins":[{"id":"pass","label":"pass","cmd":["/pfad/skript"],"placeholder":"…"}]}'
)

_conf = {"t": None, "d": {}}


def config():
    """~/.config/inquirist/config.json (wird bei Änderung neu gelesen; Fehler → leer)."""
    try:
        t = os.stat(CONF).st_mtime
    except OSError:
        _conf.update(t=None, d={})
        return _conf["d"]
    if t != _conf["t"]:
        try:
            with open(CONF, encoding="utf-8") as f:
                d = json.load(f)
            _conf.update(t=t, d=d if isinstance(d, dict) else {})
        except (OSError, ValueError):
            _conf.update(t=t, d={})
    return _conf["d"]


def ensure_config():
    if not os.path.exists(CONF):
        os.makedirs(os.path.dirname(CONF), exist_ok=True)
        with open(CONF, "w", encoding="utf-8") as f:
            json.dump({"commands": [], "snippets": [], "engines": {}, "plugins": []}, f, indent=2, ensure_ascii=False)
            f.write("\n")


def short_date(ts, allday=False):
    """heute 14:30 · morgen · mi 12.11. 09:00 · 03.01.2027"""
    if not ts:
        return ""
    d = datetime.datetime.fromtimestamp(ts) if not isinstance(ts, datetime.datetime) else ts
    today = datetime.date.today()
    delta = (d.date() - today).days
    hm = "" if allday else f" {d:%H:%M}"
    if delta == 0:
        return "heute" + hm
    if delta == 1:
        return "morgen" + hm
    if delta == -1:
        return "gestern" + hm
    if 1 < delta < 7:
        return ("mo di mi do fr sa so".split()[d.weekday()]) + f" {d:%d.%m.}" + hm
    if d.year == today.year:
        return f"{d:%d.%m.}" + hm
    return f"{d:%d.%m.%Y}"


class Debounced(Mode):
    """Modus, dessen Treffer in einem Thread gesucht werden (Eingabe bleibt flüssig): search(q) → Zeilen."""
    delay = 120

    def __init__(self, ui):
        super().__init__(ui)
        self.done_q = None
        self.pending = 0
        self.gen = 0
        self.rows_cache = []

    def show(self):
        self.done_q = None
        self.rows_cache = []

    def search(self, q):
        return []

    def rows(self, q):
        q = q.strip()
        if q != self.done_q:
            if self.pending:
                GLib.source_remove(self.pending)
            self.gen += 1
            self.pending = GLib.timeout_add(0 if self.done_q is None else self.delay, self._start, q, self.gen)
        return self.rows_cache

    def _start(self, q, gen):
        self.pending = 0

        def work():
            try:
                res = self.search(q)
            except Exception:
                res = []
            GLib.idle_add(self._done, q, res, gen)
        threading.Thread(target=work, daemon=True).start()
        return False

    def _done(self, q, res, gen):
        if gen != self.gen:
            return False
        self.done_q, self.rows_cache = q, res
        self.ui.refilter(keep=False)
        return False

    def busy(self, q):
        return q.strip() != self.done_q

    def total(self):
        return len(self.rows_cache)


# ---------------------------------------------------------------- notizen
NOTE_ROOT = os.path.join(HOME, "Documents", "notist")
NOTE_DATA = os.path.join(HOME, ".local", "share", "notes", "data", "notes")
NOTE_EXT = (".md", ".txt", ".tex", ".docx", ".odt")
TEXT_EXT = (".md", ".txt", ".tex")


class Notes(Mode):
    id, label = "notizen", "notizen"
    hint = "enter in notist öffnen   strg+⏎ ordner in filist"
    placeholder = "notiz, word-dokument oder latex suchen …  (auch im Text)"
    track = True

    def __init__(self, ui):
        super().__init__(ui)
        self.cache = {}                    # pfad → (mtime, text klein)
        self.loaded = False

    def show(self):
        def work():
            items = self._scan()
            GLib.idle_add(self._set, items)
        threading.Thread(target=work, daemon=True).start()

    def _set(self, items):
        self.items, self.loaded = items, True
        self.ui.refilter(keep=True)
        return False

    def _scan(self):
        out = []
        for dirpath, dirs, files in os.walk(NOTE_ROOT):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                if not name.lower().endswith(NOTE_EXT):
                    continue
                p = os.path.join(dirpath, name)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                text = ""
                if name.lower().endswith(TEXT_EXT) and st.st_size < 2_000_000:
                    hit = self.cache.get(p)
                    if hit and hit[0] == st.st_mtime:
                        text = hit[1]
                    else:
                        try:
                            with open(p, encoding="utf-8", errors="ignore") as f:
                                text = f.read(60000)
                        except OSError:
                            pass
                        self.cache[p] = (st.st_mtime, text)
                rel = os.path.relpath(dirpath, NOTE_ROOT)
                kind = {"notizen": "notiz", "words": "word", "latex": "latex"}.get(rel.split(os.sep)[0], rel)
                title = os.path.splitext(name)[0]
                it = Item(esc(title), dim(kind), meta=short_date(st.st_mtime), glyph="\U000F09ED", css="g-doc",
                          main=title, ident=p, data=("file", p, text.lower(), text), markup=True)
                it.mtime = st.st_mtime
                it.kind = kind
                out.append(it)
        try:
            names = os.listdir(NOTE_DATA)
        except OSError:
            names = []
        for fn in names:
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(NOTE_DATA, fn), encoding="utf-8") as f:
                    d = json.load(f)
            except (OSError, ValueError):
                continue
            if str(d.get("trashed")) == "True" or d.get("trashed") is True:
                continue
            title = d.get("title") or (d.get("text") or "").strip().split("\n")[0][:60] or "ohne titel"
            text = d.get("text") or ""
            when = d.get("updated") or ""
            try:
                ts = datetime.datetime.fromisoformat(when).timestamp()
            except ValueError:
                ts = 0
            it = Item(esc(title), dim("notiz"), meta=short_date(ts), glyph="\U000F09ED", css="g-doc", main=title,
                      ident="note:" + d.get("id", fn), data=("note", d.get("id", fn[:-5]), text.lower(), text),
                      markup=True)
            it.mtime, it.kind = ts, "notiz"
            out.append(it)
        out.sort(key=lambda i: -i.mtime)
        return out

    def message(self, q):
        return "" if self.loaded else dim("lädt …")

    def busy(self, q):
        return not self.loaded

    def rows(self, q):
        toks = q.lower().split()
        if not toks:
            return self.items[:120]
        hits = []
        for n, it in enumerate(self.items):
            s = score(it, toks)
            text = it.data[2]
            in_text = all(t in text for t in toks) if text else False
            if s is None and not in_text:
                continue
            total = (s if s is not None else 0) + (25 if in_text else 0)
            if s is None:
                total = 10
            total += self.bonus(it)
            hits.append((-total, n, it, in_text))
        hits.sort(key=lambda h: h[:2])
        rows = []
        for _s, _n, it, in_text in hits[:200]:
            it.sub = dim(f"{it.kind} · {self._snippet(it.data[3], toks[0])}") if in_text else dim(it.kind)
            rows.append(it)
        return rows

    @staticmethod
    def _snippet(text, tok):
        i = text.lower().find(tok)
        if i < 0:
            return ""
        a = max(0, i - 28)
        return ("…" if a else "") + " ".join(text[a:i + 60].split())

    def activate(self, item, q, alt=False):
        kind, ref = item.data[0], item.data[1]
        if kind == "note":
            detach("notist", "--note", ref)
        elif alt:
            fl = shutil.which("filist")
            detach(fl, os.path.dirname(ref)) if fl else detach("xdg-open", os.path.dirname(ref))
        else:
            detach("notist", ref)
        return True


# ---------------------------------------------------------------- mails
MAIL_CACHE = os.path.join(HOME, ".cache", "mailist")
MAIL_OPEN = r'''
A=de.invincible.Mailist
has() { gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
    --method org.freedesktop.DBus.NameHasOwner $A 2>/dev/null | grep -q true; }
has || { mailist --daemon >/dev/null 2>&1 & for i in $(seq 40); do has && break; sleep 0.25; done; sleep 1; }
gdbus call --session --dest $A --object-path /de/invincible/Mailist --method org.gtk.Actions.Activate \
    open-mail "[<'$1'>]" '{}' >/dev/null 2>&1
'''


def mail_accounts():
    try:
        with open(os.path.join(HOME, ".config", "mailist", "accounts.json"), encoding="utf-8") as f:
            lst = json.load(f).get("list", [])
    except (OSError, ValueError):
        lst = []
    out = []
    for a in lst:
        aid = a.get("id", "")
        db = os.path.join(MAIL_CACHE, "mail.db" if aid == "main" else f"{aid}.db")
        if os.path.exists(db):
            out.append((aid, a.get("name") or aid, db))
    return out


class Mails(Debounced):
    id, label = "mails", "mails"
    hint = "enter in mailist öffnen"
    placeholder = "mail suchen …  (betreff, absender, vorschau)"

    def search(self, q):
        toks = q.split()
        rows = []
        for aid, name, db in mail_accounts():
            try:
                con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1.0)
            except sqlite3.Error:
                continue
            try:
                where, par = ["labels NOT LIKE '%TRASH%'", "labels NOT LIKE '%SPAM%'"], []
                for t in toks:
                    where.append("(subject LIKE ? OR from_name LIKE ? OR from_addr LIKE ? OR snippet LIKE ?)")
                    par += [f"%{t}%"] * 4
                cur = con.execute("SELECT id, from_name, from_addr, subject, date, unread FROM messages WHERE "
                                  + " AND ".join(where) + " ORDER BY date DESC LIMIT 40", par)
                for mid, fn, fa, subj, date, unread in cur.fetchall():
                    who = (fn or fa or "").strip()
                    title = esc((subj or "(kein betreff)").strip()[:100])
                    if unread:
                        title = f"<b>{title}</b>"
                    it = Item(title, dim(f"{who} · {name}"), meta=human_date((date or 0) / 1000),
                              glyph="\U000F01EE" if unread else "\U000F01F0", css="g-link", main=subj or "",
                              ident=f"{aid}|{mid}", markup=True)
                    it.when = date or 0
                    rows.append(it)
            except sqlite3.Error:
                pass
            finally:
                con.close()
        rows.sort(key=lambda i: -i.when)
        return rows[:60]

    def message(self, q):
        if mail_accounts():
            return ""
        return dim("mailist ist nicht eingerichtet – noch keine mails gefunden")

    def activate(self, item, q, alt=False):
        detach("bash", "-c", MAIL_OPEN, "_", item.ident)
        return True


# ---------------------------------------------------------------- termine
EVENTS = os.path.join(HOME, ".local", "share", "kalender", "data", "cache.json")


class Events(Mode):
    id, label = "termine", "termine"
    hint = "enter in datist öffnen   strg+⏎ im browser"
    placeholder = "termin suchen …  (titel, ort, kategorie)"
    track = False

    def __init__(self, ui):
        super().__init__(ui)
        self.mtime = None
        self.loaded = False

    def show(self):
        def work():
            items = self._load()
            GLib.idle_add(self._set, items)
        threading.Thread(target=work, daemon=True).start()

    def _set(self, items):
        if items is not None:
            self.items = items
        self.loaded = True
        self.ui.refilter(keep=True)
        return False

    def _load(self):
        try:
            t = os.stat(EVENTS).st_mtime
        except OSError:
            return []
        if t == self.mtime and self.items:
            return self.items
        try:
            with open(EVENTS, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return []
        self.mtime = t
        cals = {c.get("id"): c for c in d.get("calendars", [])}
        evs = []
        for e in d.get("events", {}).values():
            cal = cals.get(e.get("cal"), {})
            if "weeknum" in (e.get("cal") or "") or e.get("status") == "cancelled":
                continue
            try:
                s = e["start"]
                allday = bool(e.get("allday"))
                start = datetime.datetime.fromisoformat(s[:10]) if allday else datetime.datetime.fromisoformat(s)
                end = datetime.datetime.fromisoformat((e.get("end") or s)[:10]) if allday else \
                    datetime.datetime.fromisoformat(e.get("end") or s)
            except (KeyError, ValueError):
                continue
            if start.tzinfo:
                start, end = start.astimezone().replace(tzinfo=None), end.astimezone().replace(tzinfo=None)
            title = e.get("title") or "(ohne titel)"
            loc = (e.get("location") or "").split("\n")[0][:60]
            it = Item(esc(title), dim(" · ".join(x for x in (loc, cal.get("name", "")) if x)),
                      glyph="\U000F00ED", css="g-code", main=title,
                      extra=f"{loc} {e.get('cat') or ''} {cal.get('name', '')}", ident=e.get("uid", title),
                      data={"html": e.get("html"), "allday": allday}, markup=True)
            it.start, it.end = start, end
            evs.append(it)
        evs.sort(key=lambda i: i.start)
        return evs

    def _window(self):
        now = datetime.datetime.now()
        lo = datetime.datetime.combine(now.date(), datetime.time())        # ab heute 0 Uhr
        return [i for i in self.items if i.end >= lo]

    def rows(self, q):
        now = datetime.datetime.now()
        pool = self._window()
        for i in pool:
            i.meta = short_date(i.start, i.data["allday"])
            i.css = "g-code" if i.end >= now else "g-file"
        toks = q.lower().split()
        if not toks:
            return pool[:80]
        return filter_items(self.items, q, limit=100)       # suchen: auch weit entfernte Termine

    def total(self):
        return len(self._window())

    def busy(self, q):
        return not self.loaded

    def message(self, q):
        if not self.loaded:
            return dim("lädt …")
        return "" if self.items else dim("keine termine – datist hat noch nichts abgeglichen")

    def activate(self, item, q, alt=False):
        if alt and item.data.get("html"):
            detach("xdg-open", item.data["html"])
        else:
            detach("datist")
        return True


# ---------------------------------------------------------------- links
def browser_dbs():
    out = []
    for pat in ("~/.config/zen/*/places.sqlite", "~/.zen/*/places.sqlite", "~/.mozilla/firefox/*/places.sqlite",
                "~/.librewolf/*/places.sqlite", "~/.var/app/org.mozilla.firefox/.mozilla/firefox/*/places.sqlite"):
        out += glob.glob(os.path.expanduser(pat))
    return out


class Links(Mode):
    id, label = "links", "links"
    hint = "enter öffnet   strg+⏎ adresse kopieren"
    placeholder = "lesezeichen oder oft besuchte seite …"
    track = True

    def __init__(self, ui):
        super().__init__(ui)
        self.t = 0
        self.loaded = False

    def show(self):
        if self.items and time.time() - self.t < 90:
            self.loaded = True
            return

        def work():
            items = self._read()
            GLib.idle_add(self._set, items)
        threading.Thread(target=work, daemon=True).start()

    def _set(self, items):
        self.items, self.t, self.loaded = items, time.time(), True
        self.ui.refilter(keep=True)
        return False

    def _read(self):
        seen, out = set(), []

        def add(title, url, mark):
            if not url or url in seen or not url.startswith(("http://", "https://")):
                return
            seen.add(url)
            host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
            t = (title or host).strip()
            it = Item(esc(t[:90]), dim(re.sub(r"^https?://(www\.)?", "", url)[:70]), glyph=mark,
                      css="g-link" if mark == "\U000F00C0" else "g-file", main=t, extra=url, ident=url, data=url,
                      markup=True)
            out.append(it)
        for db in browser_dbs():
            tmp = tempfile.mkdtemp(prefix="iq-places-")
            try:
                for suffix in ("", "-wal"):                      # laufender Browser: samt Schreibprotokoll kopieren
                    if os.path.exists(db + suffix):
                        shutil.copy2(db + suffix, os.path.join(tmp, "places.sqlite" + suffix))
                con = sqlite3.connect(os.path.join(tmp, "places.sqlite"))
                for title, url in con.execute(
                        "SELECT b.title, p.url FROM moz_bookmarks b JOIN moz_places p ON p.id = b.fk "
                        "WHERE b.type = 1 AND p.url LIKE 'http%' ORDER BY b.dateAdded DESC"):
                    add(title, url, "\U000F00C0")
                for title, url in con.execute(
                        "SELECT title, url FROM moz_places WHERE hidden = 0 AND visit_count > 1 AND url LIKE 'http%' "
                        "ORDER BY frecency DESC LIMIT 600"):
                    add(title, url, "\U000F059F")
                con.close()
            except (sqlite3.Error, OSError):
                pass
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        for path in ("~/.config/chromium/Default/Bookmarks", "~/.config/google-chrome/Default/Bookmarks",
                     "~/.config/BraveSoftware/Brave-Browser/Default/Bookmarks"):
            try:
                with open(os.path.expanduser(path), encoding="utf-8") as f:
                    root = json.load(f)["roots"]
            except (OSError, ValueError, KeyError):
                continue
            stack = list(root.values())
            while stack:
                n = stack.pop()
                if isinstance(n, dict):
                    if n.get("type") == "url":
                        add(n.get("name"), n.get("url"), "\U000F00C0")
                    stack.extend(n.get("children", []))
        return out

    def busy(self, q):
        return not self.loaded

    def message(self, q):
        if self.loaded and not self.items:
            return dim("keine lesezeichen gefunden (Zen, Firefox, Chromium werden gelesen)")
        return ""

    def total(self):
        return len(self.items)

    def activate(self, item, q, alt=False):
        if alt:
            copy(item.data, "Adresse")
        else:
            detach("xdg-open", item.data)
        return True


# ---------------------------------------------------------------- befehle
class Commands(Mode):
    id, label = "befehle", "befehle"
    hint = "enter ausführen   strg+⏎ im terminal"
    placeholder = "eigener befehl, textbaustein – oder einfach einen shell-befehl tippen …"
    track = True

    def show(self):
        self.items = self._build()

    def _build(self):
        c = config()
        out = []
        for cmd in c.get("commands", []):
            if isinstance(cmd, dict) and cmd.get("name") and cmd.get("cmd"):
                out.append(Item(esc(cmd["name"]), dim(str(cmd["cmd"])[:80]), glyph="\U000F018D", css="g-code",
                                main=cmd["name"], extra=cmd.get("keywords", "") + " befehl", ident="cmd:" + cmd["name"],
                                data=("cmd", cmd["cmd"], bool(cmd.get("terminal"))), markup=True))
        for sn in c.get("snippets", []):
            if isinstance(sn, dict) and sn.get("name") and "text" in sn:
                prev = " ".join(str(sn["text"]).split())[:80]
                out.append(Item(esc(sn["name"]), dim(prev), glyph="\U000F0219", css="g-txt", main=sn["name"],
                                extra=sn.get("keywords", "") + " baustein text", ident="txt:" + sn["name"],
                                data=("txt", sn["text"], False), markup=True))
        return out

    def rows(self, q):
        rows = super().rows(q)
        s = q.strip()
        if s:
            rows = rows + [Item(f"ausführen: {esc(s)}", dim("shell-befehl"), glyph="\U000F018D", css="g-code",
                                main="", ident="run:" + s, data=("cmd", s, False), markup=True),
                           Item(f"im terminal: {esc(s)}", dim("bleibt offen"), glyph="\U000F018D", css="g-code",
                                main="", ident="term:" + s, data=("cmd", s, True), markup=True)]
        rows.append(Item("befehle &amp; bausteine bearbeiten", dim(CONF.replace(HOME, "~")), glyph="\U000F03EB",
                         css="g-link", main="bearbeiten konfiguration einstellungen config", ident="__edit__",
                         data=("edit", "", False), markup=True))
        return rows

    def message(self, q):
        if q.strip() or self.items:
            return ""
        return dim("noch nichts eingerichtet – unten „bearbeiten“ öffnet die Datei, oder gleich einen befehl tippen")

    def total(self):
        return len(self.items)

    def activate(self, item, q, alt=False):
        kind, val, term = item.data
        if kind == "edit":
            ensure_config()
            detach("notist", CONF) if shutil.which("notist") else detach("xdg-open", CONF)
            notify("Format: " + CONFIG_HELP[:90] + " …")
            return True
        if kind == "txt":
            copy(val, f"„{item.title}“")
            return True
        argv = [str(a) for a in val] if isinstance(val, list) else ["sh", "-c", str(val)]
        if term or alt:
            line = shlex.join(argv) if isinstance(val, list) else str(val)
            detach(*terminal_cmd(), "sh", "-c", line + '; echo; read -p "enter schließt … " _')
        else:
            detach(*argv)
        return True


# ---------------------------------------------------------------- Plugin-Modi (eigene Skripte)
class Script(Debounced):
    """Modus aus config.json → "plugins": [{"id","label","cmd":[…],"placeholder","hint"}].
    Das Skript bekommt die Eingabe als letztes Argument und gibt eine JSON-Liste aus:
    [{"title","sub","meta","glyph","open":url|pfad,"copy":text,"run":[argv]}] (Zeilen ohne JSON = Texte zum Kopieren)."""

    def __init__(self, ui, spec=None):
        super().__init__(ui)
        spec = spec or {}
        self.spec = spec
        self.id = str(spec.get("id", "plugin"))
        self.label = str(spec.get("label", self.id))
        self.placeholder = spec.get("placeholder", "eingabe …")
        self.hint = spec.get("hint", "enter ausführen")
        self.err = ""

    def search(self, q):
        cmd = self.spec.get("cmd")
        if isinstance(cmd, str):
            cmd = ["sh", "-c", cmd, "_"]
        if not cmd:
            return []
        try:
            r = subprocess.run([os.path.expanduser(str(c)) for c in cmd] + [q], capture_output=True, text=True,
                               timeout=float(self.spec.get("timeout", 6)))
        except (OSError, subprocess.SubprocessError) as e:
            self.err = f"{type(e).__name__}: {e}"
            return []
        self.err = "" if r.returncode == 0 else (r.stderr.strip().splitlines() or ["fehler"])[-1]
        out = r.stdout.strip()
        try:
            data = json.loads(out) if out else []
        except ValueError:
            data = [{"title": l, "copy": l} for l in out.splitlines() if l.strip()]
        rows = []
        for n, d in enumerate(data if isinstance(data, list) else []):
            if isinstance(d, str):
                d = {"title": d, "copy": d}
            if not isinstance(d, dict) or not d.get("title"):
                continue
            rows.append(Item(esc(str(d["title"])), dim(str(d["sub"])) if d.get("sub") else "", meta=str(d.get("meta", "")),
                             glyph=str(d.get("glyph", "\U000F0349")), css="g-code", main=str(d["title"]),
                             ident=f"{self.id}:{n}:{d['title']}", data=d, markup=True))
        return rows

    def message(self, q):
        return dim(esc(self.err)) if self.err else ""

    def activate(self, item, q, alt=False):
        d = item.data
        if d.get("run"):
            detach(*[str(a) for a in d["run"]])
        elif d.get("open"):
            detach("xdg-open", str(d["open"]))
        elif d.get("copy") is not None:
            copy(str(d["copy"]), f"„{str(d['copy'])[:40]}“")
        return True
