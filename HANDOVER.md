# Handover — 31.08.2026

Stand nach der Sitzung zu GitHub-Rotation, Archivformat und manuellem
Backup-Auslöser pro Quelle.

## Ausgangslage

Der Nutzer meldete zwei Beobachtungen an den laufenden Backups:

1. Die eingestellte Rotation (3 Versionen) griff nicht.
2. GitHub legte jedes Projekt als kompletten Ordner ab statt als ein Archiv
   pro Projekt.

Beides bestätigt. Dazu kamen drei weitere Befunde, die beim Prüfen auffielen.

## Befunde und was daraus wurde

### 1. Rotation lief bei allen Git-Quellen ins Leere

`_cleanup_old_backup_versions` (`executor.py`) sucht Einträge mit
`\d{8}_\d{6}` im Namen. Die Git-Handler schrieben `user_repo.git` — ohne
Zeitstempel. Also null gefundene Versionen, nie etwas gelöscht. Es gab auch
nichts zu löschen: der Mirror wurde per `remote update --prune` überschrieben,
es existierte immer nur ein Stand. Die Rotation war nicht kaputt, sondern
gegenstandslos.

Betroffen waren auch `rsync_ssh`, `smb`, `rclone`, `local`, `ftp`, `webdav` —
alles Sync-Handler ohne Zeitstempel. **Für diese ist weiterhin nichts
geändert** (siehe „Offene Punkte").

Nebenbei: Die Einstellung heißt `backup_retention_count`, Default **10**,
nicht 3.

### 2. Ordner statt Archiv war so gebaut

Kein `tar`, kein `zip` im Handler — `git clone --mirror` legt bare Repos als
Verzeichnisse ab, fertig.

### 3. Dieselbe Lücke in `git.py`

GitLab, Gitea, Bitbucket, Codeberg, Forgejo hatten strukturgleichen Code.
Mitgezogen.

### 4. Rotation lief nicht, wenn eine Quelle fehlschlug

Der Cleanup-Aufruf stand hinter `handler.backup()` im selben `try`. Warf der
Handler, wurde die Rotation übersprungen. Eine Quelle mit abgelaufenen
Zugangsdaten hätte unbegrenzt Altstände gesammelt, während die sichtbare
Fehlermeldung von der Verbindung handelt. Im Container belegt: vorher blieben
alle 5 Stände liegen, jetzt rotiert es auch im Fehlerfall.

### 5. Kein manueller Auslöser pro Quelle

Es gab nur den Dashboard-Button für **alle** Quellen. Das Backend konnte
Einzelquellen schon (`sources`-Feld in `/backup/start`), es fehlte nur der Weg
im UI.

## Was jetzt gebaut ist

### Ablage

```
/mnt/backup/<quelle>/
  _mirrors/                              <- Arbeitskopie, nicht versioniert
    user_repo.git/
  user_repo_20260831_143000.tar.gz       <- eine Datei je Projekt und Lauf
  .user_repo.partial.tar.gz              <- nur während des Schreibens
```

Der Mirror bleibt als inkrementeller Arbeitsstand liegen, sonst müsste jeder
Lauf alles neu klonen. Die Archive tragen den Zeitstempel, auf den die
bestehende Rotation matcht.

Bestehende Mirrors werden beim ersten Lauf **verschoben, nicht neu geklont**
(`_migrate_legacy_mirror`). Im Log erscheint dann
`Moved existing mirror <repo>.git into _mirrors/`.

### Warum tar.gz und nicht zip

Gemessen an einem 37-MB-Flask-Mirror:

| Variante | Größe | vs. roh | CPU |
|---|---|---|---|
| zip -6 | 37,5 MB | 97 % | 1,25 s |
| tar.gz -6 | 37,5 MB | 97 % | 1,22 s |
| tar.zst -3 | 37,4 MB | 97 % | 0,16 s |
| tar pur | 38,7 MB | 100 % | 0,03 s |

Bei einem gepackten Mirror bringt Kompression **nichts** (3 % für die
zehnfache CPU-Zeit) — Git komprimiert seine Objekte selbst mit zlib.

Entschieden hat der Gegenfall: ein Mirror sammelt zwischen den Läufen **lose
Objekte** an (`git gc` läuft im bare Repo nicht automatisch). Dort komprimiert
tar.gz auf 38 %, zip nur auf 65 %, und `tar` pur bläht auf 193 % auf
(512-Byte-Blockrundung bei vielen Kleinstdateien). Ein Solid-Stream schlägt
einzeln deflatete Zip-Einträge deutlich.

**zstd wäre achtmal schneller bei gleicher Größe**, braucht aber ein
Extra-Paket im Image. Falls Holma auf einem Pi 3 läuft und die CPU-Zeit
spürbar wird, ist das der nächste Schritt.

### Gemeinsame Logik statt Kopie

`backend/app/backup/sources/git_archive.py` — `GitMirrorArchiveMixin` mit
`_mirror_root`, `_migrate_legacy_mirror`, `_archive_repository`. Beide Handler
erben davon. `MIRROR_DIRNAME` steht dort **einmal** und wird vom Executor
importiert, nicht zweitgetippt.

### Manueller Auslöser pro Quelle

Auf der Sources-Seite je Karte ein grüner Play-Button („Jetzt sichern"), ruft
`backupAPI.start({ sources: [id], parallel: 1 })`.

- Läuft die Quelle schon, wird der Button zum Spinner und die API weist einen
  zweiten Start mit **HTTP 409** ab. Zwei Läufe auf denselben Mirror würden ihn
  beschädigen und ihre Rotationsdurchläufe kollidieren.
- Deaktivierte Quellen: Button ausgegraut, API antwortet **409** mit
  `Sources are disabled`. Vorher hätte der Executor sie still weggefiltert und
  der Lauf hätte Erfolg gemeldet, ohne etwas zu tun.
- Unbekannte Quelle: **404**.
- Neuer Endpunkt `GET /api/v1/backup/running-sources` liefert die laufenden
  Quellen-IDs. Das UI pollt alle 3 s, aber **nur solange etwas läuft**.

**Die Rotation greift beim Einzellauf automatisch**, weil der Cleanup in
`_backup_source` sitzt und die `source_id` bekommt — unabhängig davon, wie
viele Quellen im Lauf sind. Im Container belegt: 5 Stände, Retention 3,
Einzellauf → 2 gelöscht, `_mirrors` und Teil-Datei unangetastet.

## Gate

`backend/tests/test_git_rotation.py` — **40 Prüfungen**, läuft ohne
Flask-Umgebung:

```bash
python3 backend/tests/test_git_rotation.py     # GRUEN: 40 Pruefungen bestanden
```

Eigenschaften, die beim Weiterarbeiten wichtig sind:

- **Pflegt keine Handler-Liste.** Sucht in `sources/` selbst alles, was
  `clone --mirror` aufruft. Gegengeprobt mit einem untergeschobenen fehlerhaften
  Handler — wurde von allein gefunden und mit 4 Fehlern gemeldet.
- **Dritter Ausgang.** Fehlt `git` oder eine Quelldatei: Exit 2
  („nicht gemessen"), nicht stillschweigend grün.
- **Die Doppelstart-Sperre wird ausgeführt, nicht gelesen.** Der echte
  `busy = ...`-Ausdruck wird aus `backup.py` extrahiert und gegen belegte und
  freie Quellen evaluiert. Eine reine Textprüfung blieb bei totgelegter Sperre
  grün — das war ein echter Fehlschlag in der Gegenprobe, siehe unten.
- Prüfung 4 ist ein echter Durchlauf: Repo anlegen, mirror-klonen, packen,
  entpacken, `git clone` daraus.

### Gegenprobe

14 Sabotagen einzeln gefahren — 12 im Sammellauf plus die beiden unten —,
jede mit `grep -c` auf Wirksamkeit geprüft, gesunder Lauf davor und danach grün.

**Zwei Sabotagen blieben zunächst grün und deckten blinde Prüfungen auf:**

1. *Doppelstart-Sperre totgelegt* (`busy = set()`): Die Prüfung fragte nur, ob
   `_running_source_ids()` und `409` in der Datei vorkommen — beides stand noch
   da, nur die Zuweisung war tot. Ersetzt durch Ausführung des echten Ausdrucks.
2. *Rotation aus dem Fehlerpfad entfernt*: Der Anker
   `except Exception as e:` traf ein **früheres** Vorkommen in `execute()`
   (Notification-Behandlung), der Ausschnitt enthielt dann den
   Erfolgspfad-Aufruf. Ersetzt durch Anker auf `result.status = 'failed'`.

Beide erst nach dem Umbau rot. Das ist der Grund, warum die Gegenprobe nicht
optional ist.

## Am laufenden System geprüft

Im Docker-Container gegen die echte API belegt (nicht nur am Quelltext):

- `running-sources` leer → `{"source_ids":[]}`
- unbekannte Quelle → **404**
- deaktivierte Quelle → **409** `Sources are disabled`
- gültige Einzelquelle → **202**, Lauf mit genau 1 Quelle
- Rotation im Einzellauf: 5 Archive + `_mirrors` + Teil-Datei → 3 Archive +
  `_mirrors` + Teil-Datei
- Zweiter Klick während eines laufenden Backups → **409**
- Fehlschlagende Quelle: Status `failed`, **und** Log
  `Cleanup: 2 alte Backup-Artefakte entfernt`

Frontend-Build grün (`npm run build`).

## Nicht geprüft / offene Punkte

- **Kein Lauf gegen die Produktivinstanz.** Holma läuft auf dieser
  Maschine nicht, `/mnt/backup` existiert hier nicht. Alles oben ist an einem
  Testcontainer und echten Git-Mirrors belegt, nicht am realen Datenbestand.
  → **Beim ersten Lauf nach dem Deploy ins Log schauen**, ob
  `Moved existing mirror … into _mirrors/` erscheint. Das ist die einzige
  Stelle, die vom realen Ablagezustand abhängt.

- **Sync-Handler rotieren weiterhin nicht** (`rsync_ssh`, `smb`, `rclone`,
  `local`, `ftp`, `webdav`). Sie überschreiben ein Zielverzeichnis ohne
  Zeitstempel — dieselbe Ausgangslage wie bei Git vor dieser Sitzung. Ob das
  gewollt ist (Spiegel statt Versionen), war nicht Teil des Auftrags und ist
  ungeklärt. **Nicht ungefragt umbauen**: bei 100-GB-NAS-Quellen wäre ein
  Archiv pro Lauf eine völlig andere Größenordnung als bei Git-Repos.

- **Erststart-Konflikt im Container** (vorbestehend, nicht durch diese
  Änderungen): Bei komplett leerer DB legen zwei Gunicorn-Worker gleichzeitig
  das Schema an, einer stirbt mit `Worker failed to boot`. Ein `docker start`
  danach läuft sauber. Trat bei beiden Testcontainern auf. Wäre für einen
  Erstinstallations-Pfad einen eigenen Blick wert.

- **Wiki-Archivierung**: Wikis liegen als eigene Mirrors in `_mirrors/`, werden
  aber **nicht** separat archiviert — nur das Haupt-Repo wandert ins tar.gz.
  Falls Wiki-Versionierung gebraucht wird, fehlt sie.

- **Alte flache `.git`-Ordner in der Download-Liste**: `api/backup.py` listet
  weiterhin `*.git`-Verzeichnisse als Download-Einträge. Nach der Migration
  sind dort keine mehr, der Code ist also toter Pfad — geschadet hat er nicht,
  aufgeräumt ist er nicht.

## Dateien

Neu:
- `backend/app/backup/sources/git_archive.py`
- `backend/tests/test_git_rotation.py`
- `HANDOVER.md`

Geändert:
- `backend/app/backup/sources/github.py`, `git.py` — Mixin, Mirror-Verzeichnis
- `backend/app/backup/executor.py` — `WORKING_DIR_NAMES`, Rotation im
  Fehlerpfad, Einmal-Merker
- `backend/app/api/backup.py` — `running-sources`, Doppelstart-/Disabled-/
  Unknown-Prüfung
- `frontend/src/pages/Sources.jsx` — Button, Polling, Zustände
- `frontend/src/services/api.js`, beide `translation.json`
