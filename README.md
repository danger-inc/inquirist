<!-- gh-header -->
<div align="center">

<img src="inquirist.svg" width="88" alt="inquirist">

# inquirist

**launcher with modes: apps, windows, files, calculator …**

<img src="https://img.shields.io/badge/GTK-4-4A86CF?style=flat-square&logo=gtk&logoColor=white" alt="GTK"> <img src="https://img.shields.io/badge/python-3.10+-3776AB?style=flat-square&logo=python&logoColor=white" alt="python"> <img src="https://img.shields.io/badge/platform-linux-2E7D6B?style=flat-square&logo=linux&logoColor=white" alt="platform"> <img src="https://img.shields.io/badge/made%20for-wayland%20·%20hyprland-7C6BC4?style=flat-square" alt="made for">

</div>

<p align="center"><img src="docs/inquirist.png" width="860" alt="inquirist screenshot"></p>

<p align="center"><!-- gh-note --><sub>wallpaper: [Fangpeii](https://www.pixiv.net/artworks/120232182) · via [wallhaven](https://wallhaven.cc/w/rr1kow)</sub></p>

the launcher of the -ist suite (gtk4): one input for programs, windows, files, calculator, clipboard history,
emoji/symbols, web search and system actions. it waits invisibly in the background and is there the moment you
press the key – typing is never blocked (everything slow runs in threads).

## install – linux

```bash
gh auth login                                   # login once (repository is private, invitation needed)
gh repo clone danger-inc/inquirist ~/inquirist-src
cd ~/inquirist-src && ./install.sh
```

the installer asks for the system packages (gtk4, pygobject, gtk4-layer-shell, qalc, cliphist, wl-clipboard – password
once), copies inquirist to `~/.local/share/inquirist` and creates the command `inquirist` and a menu entry. last it
asks about autostart in the background.

hyprland: `exec-once = inquirist --daemon`, `bind = SUPER, R, exec, inquirist`, blur with
`layerrule = blur, inquirist` + `layerrule = ignorealpha 0.1, inquirist`.

## usage

`inquirist [apps|fenster|dateien|rechner|ablage|zeichen|web|system]` – the same key again closes it.
tab / shift+tab (or ctrl+1…8) switch the mode, ↑↓ / ctrl+p/n move, enter runs, esc closes, click outside closes.

* **apps** – fuzzy search, most used first.
* **fenster** – every open window on every workspace and screen (hyprland only), enter jumps there, ctrl+x closes it.
* **dateien** – browse like in filist (path on top is clickable, ⌫ goes up, ctrl+h shows hidden files, ctrl+enter
  opens in filist); typing also searches the subfolders. `/…` or `~/…` types a path.
* **rechner** – calculates while you type (`12% von 80`, `5 km in mi`, `100 eur in usd`), enter copies.
* **ablage** – clipboard history (cliphist), enter copies again.
* **zeichen** – emoji and symbols, german and english names.
* **web** – text + enter searches; prefix `g`, `yt`, `w`, `gh`, `aw`, `aur`, `maps`, `dict` picks the site.
* **system** – lock, suspend, log out, reboot, power off, wifi, bluetooth, do-not-disturb, screenshot, …
  (only what exists on the system is offered).

## runs on

| system | status |
| --- | --- |
| arch (hyprland) | tested |
| sway/kde (layer-shell), ubuntu 24.04+, fedora 40+, openSUSE | should work (no window list) |
| gnome | opens as a normal window instead of a layer |
| windows | not supported (needs wayland layer-shell; windows has its own run box) |

## update / remove

```bash
cd ~/inquirist-src && ./update.sh
./uninstall.sh
```

<!-- gh-suite -->
## the -ist suite

all apps share one look (terminal style, colors from your wallpaper via matugen), one installer and the same shortcuts.

| app | what it does |
| --- | --- |
| [scourge](https://github.com/danger-inc/scourge-public) | inspect, edit, record, cut – and installs the others |
| [notist](https://github.com/danger-inc/notist-public) | notes · words · latex |
| [filist](https://github.com/danger-inc/filist-public) | file explorer + file dialog |
| [datist](https://github.com/danger-inc/datist) | calendar |
| [mailist](https://github.com/danger-inc/mailist-public) | mail |
| [musicalist](https://github.com/danger-inc/musicalist-public) | youtube music |
| [linguist](https://github.com/danger-inc/linguist) | translator + hover corner |
| [sharist](https://github.com/danger-inc/sharist) | quick share |
| [wallist](https://github.com/danger-inc/wallist) | wallpapers |

dotfiles with the matching hyprland setup: [danger-inc/dotfiles](https://github.com/danger-inc/dotfiles)
