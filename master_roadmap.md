# Holma - Master Roadmap

## Done
- [x] CI: Frontend-Multiarch-Build führt Node auf der nativen Builder-Architektur aus statt ARM64-`npm ci` unter QEMU
- [x] Security/UI: Offline-Ersteinrichtung mit frei wählbarem Konto und lokalem Einmal-Code, Container-Passwort-Reset, README und SVG-Logo-Anzeige korrigiert
- [x] UI: Neues Holma-Vektorlogo in Holma-Blau (#0284c7) implementiert, abgeleitete PWA-/Favicon-/App-Icons generiert und Dark Mode adaptiert
- [x] Fix: rclone-Backups verwenden nicht-löschendes `copy` statt zielbereinigendem `sync`
- [x] Security: Passwortgebundene Automation-Tokens mit 365-Tage-Limit und Widerruf bei Passwortänderung ergänzt
- [x] Fix: Mehrprozess-Start über Dateisperre serialisiert und SQLite-Race mit 4-Prozess-Regressionstest abgesichert
- [x] Qualität: Backend-/Frontend-Abhängigkeiten aktualisiert; npm-, pip- und Bandit-Audits ohne bekannte hohe oder mittlere Befunde
- [x] UI: Alle sichtbaren Source-/Restore-Texte DE/EN lokalisiert, ESLint-9-Gate repariert und Routen per Lazy Loading aufgeteilt
- [x] Deployment: Host-/Tailscale-DNS wird in Compose geerbt; hartcodierte öffentliche DNS-Server entfernt
- [x] Doku: README-Testmatrix, USB-Automation, API-Verträge, Plattformen und Entwicklungsbefehle an den validierten Stand angepasst
- [x] Fix: Alle Backup-Handler lesen UI-Werte konsistent aus dem abgeflachten `config`-Sub-Objekt
- [x] Fix: Webinstaller auf localhost und festes Projektverzeichnis begrenzt, mit Einmal-Token/Phasenfolge geschützt und bestehende `.env` bewahrt
- [x] Fix: Restore-Jobs verschlüsselt unter `/data` persistiert, über den dedizierten Worker ausgeführt und bei Neustart sicher finalisiert
- [x] Fix: Restore-Polling behandelt Queue-, Netzwerk- und Abbruchzustände begrenzt statt endlos weiterzulaufen
- [x] UI: Neue Markenassets für GitHub-README, Login, Navigation, Favicon, Apple-Touch-Icon und PWA-Manifest integriert
- [x] Fix: Standard-UI und Doku auf 35 tatsächlich unterstützte Source-Typen begrenzt; Portainer-Export ausschließlich read-only über API-Key
- [x] Deployment: Backend-Image enthält die benötigten Standard-Clients und wird per CI für ARM64 und AMD64 gebaut
- [x] Fix: SQLite-Backup schließt Quell- und Zielverbindung nach konsistenter Online-Sicherung zuverlässig
- [x] Fix: Source- und Notification-Secrets verschlüsselt, API-Ausgaben redigiert und CLI-Credentials aus Prozessargumenten entfernt
- [x] Fix: Admin-/Viewer-Rechte, abgesicherter Setup-Pfad und Token-Widerruf nach Passwortänderung umgesetzt
- [x] Fix: Laufzeit-Settings, atomarer Config-Import, HTTPS-/Proxy-Schalter und korrekte Verbindungstests umgesetzt
- [x] Fix: SMB ohne privilegierten CIFS-Mount über `smbclient`; SSH-, Git-, Datenbank-, Docker- und SQLite-Handler gehärtet
- [x] Fix: Backup-Jobs atomar pro Source reserviert, über eigenen Worker ausgeführt und bei Stop/Worker-Neustart dauerhaft finalisiert
- [x] Fix: Parallelität gegen das Laufzeitlimit validiert; geplante und manuelle Jobs nutzen dieselbe prozessübergreifende Sperre
- [x] Fix: Backup-Ergebnisvertrag validiert Handler-Rückgaben und persistiert Teilfehler wahrheitsgetreu als `partial`/`failed`
- [x] Fix: Local/SMB/FTP/WebDAV/Git/Proxmox/Supabase/Selfhosted propagieren Prozess- und Teilfehler statt falschem Erfolg
- [x] Fix: Docker startet für Backups gestoppte Container auch im Fehlerpfad neu; Redis streamt Remote-RDB und SQLite nutzt die konsistente Backup-API
- [x] Fix: Source-IDs und alle daraus gebildeten Backup-/Download-/Restore-Pfade zentral validiert
- [x] Fix: Supabase-Restore gegen TAR-Link-Ausbruch, leere Restore-Pläne und falsche psql-Erfolgsmeldungen gehärtet
- [x] Fix: Backup-Handler außer Supabase/GitHub akzeptieren UI-Listen, direkte Credentials und `path`-Fallbacks robuster
- [x] UI: Frontend adaptiv gehärtet mit konsistenten Touch-Zielen, sichtbarem Fokus, stabilen Dialogen und responsive Listen-/Kartenlayouts
- [x] Fix: Sprachwahl in Sidebar sichtbar gemacht und Settings-/Storage-/Config-Texte vollständig über i18n geführt
- [x] Fix: Backup-Aufbewahrung pro Quelle als UI-Setting ergänzt, Auto-Cleanup erklärt und Version auf 1.6.1 erhöht
- [x] Dark Mode für komplettes Frontend mit Systemerkennung, Toggle und globalen Kontrast-Overrides umgesetzt
- [x] Projekt-spezifische `AGENTS.md` mit Holma-Arbeitsregeln erstellt
- [x] Fix: Security-/Runtime-Bugs aus Tiefenanalyse behoben (Admin-Bootstrap, Supabase Full, Restore-Pfade, Config-Export, Source-Verträge, Notifications-Auth)
- [x] Global Credentials System (encrypted in DB)
- [x] Log Viewer im Frontend (System Logs Seite)
- [x] Security Hardening (Fernet encryption, input sanitization, capability reduction)
- [x] GitHub Backup funktional (Mirror Clone)
- [x] Version Number in Sidebar
- [x] Credentials Hint bei Source-Erstellung
- [x] Simplified Deployment (nur 4 Env Vars)
- [x] Fix: duplicate logging
- [x] Fix: datetime naive/aware mismatch
- [x] Fix: config sub-object in GitHub handler

## In Progress
- [ ] DiskStation-Live-Gates: Tailscale, dedizierte SMB-Testfreigabe sowie Docker-/Portainer-Lesezugriffe ohne bestehende Workloads zu verändern

## Done (Supabase & Restore)
- [x] **Supabase Source im Frontend:** Neue Kategorie "Cloud Platforms" mit Config-Formular (Project Ref, Region, Backup Mode)
- [x] **Suchfunktion in SourceModal:** Globale Suche über alle 35 Standard-Source-Typen (nach Label, Kategorie, Value)
- [x] **Supabase Verbindungstest:** Button in Source-Config + Backend-Endpoint mit pg_dump/psql Validierung
- [x] **Supabase Restore Backend:** `SupabaseRestore` Klasse (Schema, Data, Roles, Auth, Storage)
- [x] **Supabase Storage Metadaten:** Full-Backup sichert Bucket-/Objektmetadaten separat und Restore erhält Content-Type/Cache-Control mit Teilfehler-Status
- [x] **Restore API Endpoints:** Available Backups auflisten, Restore starten, Status-Polling
- [x] **Restore UI in History:** Restore-Button bei Supabase-Sources, Modal mit Ziel-Konfiguration, Bestätigungsdialog
- [x] **Restore Frontend API:** restoreAPI Service (getAvailable, start, getStatus)

## Future Features
- [ ] **Inkrementelle Backups:** Nur bei Änderungen sichern (GitHub: nur wenn neue Commits)
- [ ] **Backup-Rotation:** Max. Versionen pro Source (Standard: 3, einstellbar)
- [ ] **Scheduling:** Cron-artig pro Source oder global (täglich, stündlich, wöchentlich)
- [ ] **Per-Source Scheduling:** Individuelle Backup-Intervalle pro Quelle
- [ ] **Archivierung:** Optional tar.gz nach Backup erstellen
- [ ] **Notification Channels:** Telegram, Email, ntfy über Web UI konfigurierbar
- [ ] **Multi-Repo GitHub:** Alle Repos eines Users/Org auf einmal sichern (discovery_mode: all)
- [ ] **Storage Dashboard:** Speicherplatz-Übersicht pro Source mit Trends
- [ ] **Restore für weitere Source-Typen:** Docker, MySQL etc.
