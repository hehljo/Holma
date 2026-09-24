# AGENTS.md

Lokale Arbeitsanweisungen für `/root/Holma`. Globale Regeln aus `/root/.codex/AGENTS.md` gelten weiter und haben Vorrang.

## Projektbild

- Holma ist ein selbst gehosteter Multi-Source-Backup-Manager.
- Backend: Flask 3.1, SQLAlchemy, SQLite, Gunicorn, Blueprints unter `/api/v1`.
- Frontend: React 18, Vite, Tailwind CSS, i18next, lucide-react.
- Deployment: Docker Compose, Synology/Portainer, Raspberry Pi und generische Linux/Docker-Hosts.
- Zielbild: robuste Backups, einfache Web-UI, verschlüsselte Zugangsdaten, Restore für ausgewählte Quellen.

## Wichtige Dateien

- Roadmap: `MASTER_ROADMAP.md` und gespiegelt `master_roadmap.md`.
- Backend-Einstieg: `backend/app/__init__.py`, `backend/run.py`.
- Backup-Core: `backend/app/backup/base.py`, `backend/app/backup/executor.py`.
- Handler: `backend/app/backup/sources/`.
- API: `backend/app/api/`.
- Modelle: `backend/app/models/backup.py`.
- Frontend: `frontend/src/App.jsx`, `frontend/src/pages/`, `frontend/src/components/`, `frontend/src/services/api.js`.
- i18n: `frontend/src/locales/de/translation.json`, `frontend/src/locales/en/translation.json`, Backend-PO-Dateien unter `backend/app/translations/`.

## Arbeitsablauf

- Vor Änderungen kurz `git status --short` prüfen.
- Vor Code-Nutzung immer echte Signaturen und vorhandene Patterns im Quellcode lesen, ned aus dem Gedächtnis.
- Bei Backend-Änderungen zuerst betroffene API, Handler und Modellkette prüfen.
- Bei Frontend-Änderungen betroffene Komponente, API-Service und beide Locale-Dateien prüfen.
- Jede umgesetzte Code-Änderung in `MASTER_ROADMAP.md` als Checklisteneintrag protokollieren.
- Da aktuell beide Roadmap-Dateien existieren und identisch sind, Änderungen an `MASTER_ROADMAP.md` auch in `master_roadmap.md` spiegeln.
- Keine Commits oder Pushes ohne ausdrückliche Freigabe in der aktuellen Session.

## Offener Schwerpunkt

- Aktueller In-Progress-Punkt: alle Backup-Handler auf das `config`-Sub-Objekt-Problem prüfen.
- `BackupHandler.__init__` flacht `source_config["config"]` bereits in `self.source_config` ab. Neue Handler sollen `self.source_config.get(...)` nutzen und nicht direkt voraussetzen, dass Werte nur top-level oder nur unter `config` liegen.
- Frontend speichert Source-spezifische Werte typischerweise unter `formData.config`.

## Backend-Regeln

- Alle Backup-Handler erben von `BackupHandler` und liefern ein Dict mit `files_synced`, `size_synced`, `logs`.
- Handler im Registry-Mapping von `BackupExecutor.handlers` registrieren, wenn neue `type`-Werte dazukommen.
- Live-Logs laufen über `handler.log(...)`; nicht direkt printen, außer Startup/Bootstrap braucht stdout.
- Credentials über `_get_env_credential(...)` oder Settings-API-Pfade holen; Secrets nie loggen, nie in Roadmap/Doku ausschreiben.
- Datenverlust vermeiden: keine Backups, Quellen, DB-Dateien, Logs oder Configs löschen, ohne vorher zu fragen.
- Bei Datenbank-/Schemaänderungen zuerst Migrationsrisiko prüfen. Keine automatische Löschung oder Neuinitialisierung von User-Daten.
- Zeitstempel konsistent behandeln; vorhandenes Projekt hat bereits Fixes zu naive/aware datetime.
- Fehler sauber als API-JSON zurückgeben und serverseitig mit Kontext loggen, aber ohne Secrets.

## Frontend-Regeln

- Bestehendes nüchternes Dashboard-Design beibehalten: Tailwind, kompakte Panels, lucide Icons.
- Keine Marketing-Landingpage bauen; erste Ansicht bleibt die nutzbare App.
- Neue Source-Typen in `SOURCE_TYPES`, ggf. Credential-Mapping, Formularfeldern, API-Service und Übersetzungen ergänzen.
- Neue sichtbare Texte immer in Deutsch und Englisch pflegen.
- Auth-Fehlerlogik in `frontend/src/services/api.js` beachten: Connection-Tests dürfen nicht automatisch ausloggen.
- Bei Icons bevorzugt `lucide-react`; App-Icon liegt unter `frontend/public/icon.png` und `icon/icon.png`.

## Security und Daten

- `SECRET_KEY` ist Pflicht; keine unsicheren Defaults wieder einführen.
- Zugangsdaten werden über Settings verschlüsselt gespeichert, Env Vars sind Fallback.
- Docker-Socket, Restore, Import/Export, Delete-All, Log-Clear und Config-Schreibzugriffe sind riskant: vor destruktiven Aktionen fragen.
- Pfadzugriffe gegen Traversal und unzulässige Host-Pfade absichern.
- Rate Limits und Auth-Decorator bei neuen API-Endpunkten bewusst setzen.

## Tests und Checks

- Backend-Syntaxcheck: `python -m compileall backend/app`.
- Frontend-Build: `cd frontend && npm run build`.
- Frontend-Lint nur nutzen, wenn Dependencies installiert sind: `cd frontend && npm run lint`.
- Docker-Check nach Deployment-Änderungen: `docker compose config`.
- Bei Handlern möglichst mit Beispiel-Source aus `config/` oder einer minimalen Testkonfiguration prüfen.

## Roadmap-Protokoll

- Format: Checklisteneintrag unter passender Sektion.
- Fertige Code-Änderungen unter `Done`, laufende Arbeit unter `In Progress`, Ideen unter `Future Features`.
- Einträge knapp und konkret schreiben, z. B. `- [x] Fix: Docker-Handler liest Werte aus config-Sub-Objekt`.
- Roadmap nicht als Changelog aufblasen; nur umgesetzte oder bewusst geplante Projektpunkte eintragen.


## Agent-Modus & Orchestrierung
- Empfohlener Modus: Subagent-Orchester
- Kriterien: Frontend/Backend getrennt, 87 Quelldateien, Test-Suite vorhanden (87 Quelldateien)
- Workflow: Vor größeren Aufgaben kurz beim User rückversichern, ob Single Agent oder Subagents (Scout/Planner/Worker/Reviewer) eingesetzt werden.
