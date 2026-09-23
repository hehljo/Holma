# Handover — 23.09.2026

Stand nach der Sitzung „Umbenennung auf Holma + ein Artefakt pro Lauf".
Alles ist auf `main` gepusht (`1c312fa`), Repo heißt jetzt `hehljo/Holma`.

## Wichtig vorab

- **Das Repo ist bereits PUBLIC** (laut `gh repo view`). Der Nutzer ging davon
  aus, es sei privat. Nichts mehr umzuschalten, aber die Historie ist sichtbar.
- **CI-Lauf nach dem Push nicht abgewartet** (Wochenbudget 93 %). Zuerst
  prüfen: `gh run list -R hehljo/Holma -L 1`. Der neue Job `gates` läuft vor
  den Image-Builds; wird er rot, bauen keine Images.

## Was gebaut ist

### Ein Artefakt pro Lauf (`backend/app/backup/artifacts.py`)
Der Executor gibt dem Handler ein Staging- bzw. Arbeitsverzeichnis und macht
danach genau ein Artefakt daraus. Modus je Handler (`ARTIFACT_MODE` /
`artifact_mode()`):

| Modus | Quellen | Ergebnis |
|---|---|---|
| `archive` (Default) | Git-Plattformen, DBs, Supabase, Docker, Self-hosted | `<id>_<ts>.tar.gz`, Git: je Repo ein Archiv darin |
| `snapshot` | NFS, rsync, rclone, FTP/SFTP, WebDAV, local, Self-hosted mit `rsync` | `<id>_<ts>/` per `rsync --link-dest`, Arbeitskopie `_current/` |
| `folder` | SMB (smbclient-Tar), Proxmox | Staging wird nur umbenannt, kein zweites gzip |

- Fehlgeschlagener Lauf → kein Artefakt, Staging weg.
- Rotation: `select_expired()` (reine Funktion, von Executor und Gates genutzt).
  Default **3** steht nur in `DEFAULT_BACKUP_RETENTION_COUNT`.
- Restore entpackt ein inneres `supabase_*.tar.gz` im Laufarchiv
  (`_unwrap_nested_archive`), Liste zeigt alle `*.tar.gz` der Quelle.
- Keine Migration alter Ablagen (Nutzer setzt neu auf). Alte lose Dateien mit
  Zeitstempel rotieren über ihren Stempel mit raus.

### Umbenennung
- Sichtbar/Deploy: Holma überall (Docker-Images `holma/*`, Container
  `holma-backend`, GHCR `holma-*`, Skripte, Doku, README inkl. „Why Holma?").
- Eine Quelle: `frontend/src/brand.js`, `backend/app/brand.py`. `index.html`
  hat Platzhalter, das Web-Manifest erzeugt das Brand-Plugin in `vite.config.js`.
- **Bewusst NICHT umbenannt** (Verträge): `backupgenie.db`, Lock-/Logpfade im
  Container (`/var/log/backupgenie`), Crypto-Salt, Temp-Präfixe,
  `RCLONE_CONFIG_BACKUPGENIE_*`.
- Version **2.0.0**: `frontend/package.json` + `backend/app/version.py`
  (Health-Endpoint). Das Brand-Gate prüft Gleichheit.

### Gates
- `scripts/run-gates.sh` — findet Gates selbst (`backend/tests/test_*.py`,
  `scripts/gates/*.py`) + Frontend-Lint/Build; „nicht gemessen" und
  „0 Gates" sind rot. Lokal: `PYTHON=<venv>/bin/python scripts/run-gates.sh`
  → 11/11 grün.
- Neu: `backend/tests/test_run_artifacts.py` (17 Tests, echte Dateien),
  `scripts/gates/brand_gate.py` (alter Name sichtbar, Marke fest im
  Anzeigepfad, handgepflegtes Manifest, Versionsdrift, Version im Markup).
- `test_git_rotation.py` ruft jetzt die echte Funktion statt eine Regex aus
  dem Quelltext nachzubauen.
- Gegenprobe: 16 Sabotagen, 15 rot. Grün blieb nur „Arbeitsordner nicht aus
  der Rotation ausnehmen" — die Namen tragen keinen Zeitstempel, die Zeile
  ist reine Absicherung.

## Offene Punkte

1. **Logo** (macht der Nutzer): neues Bild als `frontend/public/logo-mark.png`
   ablegen; Favicon/PWA-Icons (`favicon.png`, `apple-touch-icon.png`,
   `pwa-*.png`, `icon.png`) und `icon/*.png` zeigen noch den Geist bzw. den
   alten Namen. Ggf. Generator für die abgeleiteten Größen bauen
   (Skill `game-asset-generator`).
2. **SMB-NAS = volle Kopie pro Version** (smbclient-Tar). Sparsam ginge nur
   mit Mount + Snapshot-Modus — eigener Umbau, mit Nutzer klären.
3. **Erster echter Lauf nach Neuaufsetzen:** je Quelle genau ein neues
   Artefakt? GitHub-Log: `Moved existing mirror … into _mirrors/` taucht nur
   bei Altbestand auf.
4. Doppelte Roadmap (`MASTER_ROADMAP.md` + `master_roadmap.md`) und diese
   `HANDOVER.md` liegen im öffentlichen Repo — Nutzer entscheiden lassen.
5. Roadmap-Idee (nur vorgemerkt): DiskStation-Direktanbindung per
   Synology-API + 2FA aus Henga/Lugga übernehmen.
6. Alte lokale Images `backupgenie/*` liegen noch auf dieser Maschine.
