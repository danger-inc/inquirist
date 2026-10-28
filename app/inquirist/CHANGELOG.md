# inquirist – Änderungen

## 1.4.0 (2026-10-29)
- **Reihenfolge nach Nutzung**: Was du oft und zuletzt wählst, rückt bei gleicher Trefferqualität nach oben – in apps, dateien, zeichen, system und den neuen Modi. Ohne Eingabe stehen die meistbenutzten Einträge vorn.
- **Neue Modi**: **notizen** (notist-Notizen, Words und LaTeX, auch im Text gesucht, Enter öffnet in notist), **mails** (alle mailist-Konten, Enter springt zur Mail), **termine** (datist, ab heute; Strg+⏎ im Browser), **links** (Lesezeichen und oft besuchte Seiten aus Zen/Firefox/Chromium; Strg+⏎ kopiert die Adresse) und **befehle** (eigene Befehle und Textbausteine; jeder getippte Text kann auch gleich als Shell-Befehl laufen, Strg+⏎ im Terminal).
- **Eigene Einstellungen** in `~/.config/inquirist/config.json`: `commands`, `snippets`, eigene Suchseiten für den web-Modus (`engines`) und **Plugin-Modi** (`plugins`: ein Skript bekommt die Eingabe und gibt eine JSON-Liste aus). Unten im befehle-Modus öffnet „bearbeiten“ die Datei.
- **Vorschaubilder**: Bilder in dateien und in der Zwischenablage zeigen eine kleine Vorschau statt des Symbols.
- Breiteres Fenster, Reiter lassen sich scrollen und der gewählte Reiter bleibt sichtbar; Alt/Strg+9 wählt notizen.

## 1.3.0 (2026-10-27)
- **Wechsel-Animation**: Der Wechsel zwischen Hell und Dunkel (und zwischen Designs) läuft als Scanbalken über den ganzen Bildschirm. Alle Fenster, die Leiste und das Terminal wechseln darunter im selben Moment, hinter dem Balken steht das neue Design. An/aus und Dauer (Standard 1,5 s) stehen in der Designauswahl der Einstellungen.
- Im System-Modus „design: …“ wechselt das Design mit der Animation.

## 1.2.0 (2026-10-27)
- **Rechner → divist**: Im Modus „rechner“ gibt es eine Zeile „in divist öffnen“ – sie übergibt die Eingabe an divist (den Taschenrechner mit Brüchen, Gleichungen, Ableitungen und Graph). Ohne Eingabe öffnet „divist“ den Rechner leer.

## 1.1.0 (2026-10-26)
- **Design wählbar**: In den Einstellungen gibt es die Designauswahl wie in notist (Automatisch + 9 Designs). Die Wahl gilt für alle -ist-Apps zugleich und wirkt sofort. Bei „Automatisch“ (Desktop-Farben) kannst du zwischen **Dunkel** und **Hell** umschalten. Im Modus „system“: „design …“ eintippen.

## 1.0.0 (2026-10-25)
- **Erste Ausgabe**: der Starter der Suite (ersetzt rofi). Läuft unsichtbar im Hintergrund und ist beim Tastendruck
  sofort da; Eingaben werden nie blockiert.
- Modi: **apps**, **fenster** (alle Fenster aller Arbeitsflächen und Bildschirme), **dateien** (wie filist, mit
  Tiefensuche), **rechner** (rechnet beim Tippen), **ablage**, **zeichen**, **web**, **system**.
