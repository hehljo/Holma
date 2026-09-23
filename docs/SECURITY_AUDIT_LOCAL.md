# Holma – interner Sicherheits- und Funktionsaudit

Stand: 01.09.2026  
Status: Lokale Remediation abgeschlossen; reale Zielsystemtests offen  
Veröffentlichung: Erst nach den vereinbarten DiskStation-Live-Gates.

## Ziel

Dieser Audit bewertet, ob Holma Backups und Restores korrekt, nachvollziehbar
und ohne unnötiges Risiko ausführt. Die Liste ist zugleich die verbindliche
Remediation-Checkliste. Ein Punkt gilt erst als erledigt, wenn Codefix und passende
Regressionstests grün sind.

## Blocker

- [x] **BG-AUD-001 – Unzuverlässiger Backup-Erfolgsstatus:** Mehrere Handler
  schlucken Einzel- oder Prozessfehler; der Executor kann den Lauf trotzdem als
  `completed` markieren.
- [x] **BG-AUD-002 – Unsicherer Restore-Erfolg:** PostgreSQL-Fehler auf stderr,
  leere Restore-Pläne und Teilfehler können fälschlich als erfolgreich gelten.
- [x] **BG-AUD-003 – Archiv-Ausbruch:** TAR-Symlinks/Hardlinks können beim Restore
  außerhalb des vorgesehenen Zielverzeichnisses schreiben.
- [x] **BG-AUD-004 – Unsichere Source-IDs:** Benutzerdefinierte Source-IDs können
  Backup-, Download- und Restore-Pfade aus dem Backup-Root herausführen.
- [x] **BG-AUD-005 – Prozesslokale Job-Steuerung:** Daemon-Threads, mehrere
  Gunicorn-Worker und prozesslokale Stop-Zustände erlauben Doppelstarts, verlorene
  Jobs und unzuverlässiges Stoppen.
- [x] **BG-AUD-006 – Deployment unterstützt beworbene Handler nicht:** Im
  Standard-Image fehlen Programme und teilweise Rechte für mehrere NAS-, Docker-
  und Datenbank-Handler.

## Hohe Priorität

- [x] **BG-AUD-007 – Source-Secrets:** Source-Zugangsdaten werden unverschlüsselt
  gespeichert, per API zurückgegeben und können in Logs erscheinen.
- [x] **BG-AUD-008 – Fehlende Rollen-/Rechteprüfung:** Jeder angemeldete Account
  kann administrative und destruktive Funktionen aufrufen; Registrierung und
  Passwortwechsel sind unzureichend abgesichert.
- [x] **BG-AUD-009 – Settings ohne Laufzeitwirkung:** Backup-Pfad, Parallelität,
  Log-Aufbewahrung und HTTPS-Einstellungen werden teilweise gespeichert, aber
  nicht vom laufenden System verwendet.
- [x] **BG-AUD-010 – Defekter Config-Import/-Export:** Redaktionsmarker können als
  echte Zugangsdaten importiert werden; Einstellungen werden nur teilweise oder
  nicht atomar übernommen.
- [x] **BG-AUD-011 – Falscher Verbindungstest:** Nicht implementierte Source-Tests
  liefern HTTP 200 und werden im Frontend als Erfolg dargestellt.
- [x] **BG-AUD-012 – Überzeichnete Source-Unterstützung:** Zahlreiche UI-Typen
  besitzen keinen vollständigen Handler-, Formular- oder Credential-Vertrag.
- [x] **BG-AUD-013 – Handler-spezifische Datenrisiken:** Unter anderem können
  Docker-Container nach Fehlern gestoppt bleiben, Git-Tokens in Mirrors landen,
  Live-SQLite-Kopien inkonsistent sein und Thread-parallele Handler globale
  Credential-Umgebungsvariablen teilen.
- [x] **BG-AUD-014 – Unsicherer Webinstaller:** Die Weboberfläche des Installers
  ist netzwerkweit erreichbar und kann Docker Compose aus einem auswählbaren
  lokalen Verzeichnis starten.
- [x] **BG-AUD-015 – Notifications-Vertragsbruch:** In der UI gespeicherte
  Credentials werden vom Notification-Manager nicht konsistent gelesen; einzelne
  Fehlerpfade können sensible URL-Bestandteile loggen.
- [x] **BG-AUD-016 – Unsichere Standardkonfiguration:** Das SECRET_KEY-Beispiel
  enthält einen von Compose nicht ausgeführten Shell-Ausdruck und kann dadurch zu
  identischen Schlüsseln führen.

## Mittlere Priorität und Qualität

- [x] **BG-AUD-017 – Restore-Status nur in `/tmp`:** Status und Threads sind bei
  Neustart verloren; Frontend-Polling behandelt verlorene Jobs unzureichend.
- [x] **BG-AUD-018 – Source-Konfiguration inkonsistent:** `config`-Sub-Objekt,
  Credential-Fallbacks und UI-Felder sind nicht für alle Handler deckungsgleich.
- [x] **BG-AUD-019 – Abhängigkeiten:** Python- und Frontend-Abhängigkeiten haben
  bekannte Sicherheitsmeldungen und müssen aktualisiert sowie erneut geprüft
  werden.
- [x] **BG-AUD-020 – Lint/Tests:** ESLint 9 ist nicht konfiguriert; es fehlen
  belastbare Unit-, Fehlerpfad-, Handler- und Restore-Integrationstests.
- [x] **BG-AUD-021 – Frontend-Qualität:** Sichtbare Texte umgehen teilweise i18n,
  Restore-Polling kann hängen und das Produktionsbundle braucht Aufteilung.
- [x] **BG-AUD-022 – Installationsskripte/Doku:** USB-Token-Anleitung, Cleanup-
  Verhalten und einzelne README-Befehle stimmen nicht mit dem Produkt überein.

## Bisherige Verifikation

- Backend-Syntax und vollständige Suite: grün, 60/60 Tests mit Warnungen als Fehler
- Mehrprozess-Startgate: vier parallele App-Initialisierungen auf einer frischen
  SQLite-Datenbank sowie reales Image mit zwei Gunicorn-Workern, Worker und
  Scheduler grün
- Frontend-Lint: grün, 0 Fehler und 0 Warnungen
- Frontend-Build: grün, route-basiert aufgeteilt; Hauptbundle 354,81 kB
- Docker-Compose-Konfiguration und ARM64-Image-Build: grün
- Finales Backend-Image: Health, Admin-Login und alle benötigten CLI-Werkzeuge grün
- Shell-, Python-, JSON-, Manifest- und Bilddimension-Gates: grün
- Locale-Key-Parität DE/EN: 454/454
- Dependency-Audit am 01.09.2026: `npm audit` 0 Schwachstellen;
  `pip-audit` 0 bekannte Schwachstellen
- Statischer Security-Gate: Bandit 0 hohe und 0 mittlere Funde
- Sicher reproduziert: unsichere Source-ID, Secret-Rückgabe, ignorierte Settings,
  fehlerhafter Config-Import, TAR-Ausbruch und falscher PostgreSQL-Restore-Erfolg
- Remediation-Gate Pfade/Restore: 11/11 Regressionstests grün
- Remediation-Gate Ergebnisvertrag/Handler: 22/22 Regressionstests grün;
  Fehlerpfade werden als `partial` oder `failed` persistiert
- Remediation-Gate Jobsteuerung: 9/9 Regressionstests grün; atomare
  Source-Reservierung, persistentes Stoppen und Worker-Recovery geprüft
- Remediation-Gate Auth/Secrets/Settings: 11/11 Regressionstests grün;
  Rollen, Token-Widerruf, atomare Settings/Imports und verschlüsselte Secrets geprüft
- Remediation-Gate Restore-Jobs: 4/4 Regressionstests grün; verschlüsselte
  Persistenz, Worker-Claim, Neustart-Finalisierung und Pfadvalidierung geprüft
- Webinstaller-Gate: Shell- und eingebettete Python-Syntax grün; live nur
  `127.0.0.1`, Root/API ohne Token jeweils HTTP 403 und mit Token HTTP 200
- Automation-Token-Gate: Passwort-Reauthentifizierung, maximale Laufzeit von 365
  Tagen und Widerruf durch Passwortänderung geprüft
- rclone-Gate: Backups verwenden nicht-löschendes `copy`; S3-Secrets bleiben aus
  Prozessargumenten und Logs

## Noch nicht gemessen

- Authentifizierter SMB-Backup-Lauf auf einer dedizierten Testfreigabe
- Authentifizierter Portainer-Stack-Export und read-only Docker-Engine-Abfrage
- Reale Datenbank- und Cloud-End-to-End-Läufe
- Restore auf echten Zielsystemen

## DiskStation-Live-Vorgate am 01.09.2026

- Tailscale: direkte Verbindung zu `diskstation`, 17 ms
- DSM: HTTPS auf Port 5001 liefert HTTP 200
- SMB: Dienst erreichbar, anonymer Zugriff korrekt mit Login-Fehler abgewiesen
- Portainer: öffentliche Status-API auf HTTP-Port 9000 erreichbar; Port 9443
  geschlossen. Der Source muss für diese NAS daher mit Port 9000 und ohne HTTPS
  konfiguriert werden.
- Docker: SSH-Port 22 geschlossen; ohne Portainer-API-Key oder anderen expliziten
  read-only Zugang wurde die Engine nicht abgefragt.
- Es wurden auf der DiskStation weder Daten geschrieben noch gelöscht und keine
  Container, Images, Volumes oder Stacks verändert.

Die verbleibenden Tests erfolgen erst mit dedizierter Testfreigabe und passenden
read-only Zugangsdaten. Für die DiskStation gilt: nur lesen und neue Testdaten
schreiben; keine Dateien,
Freigaben, Container, Images, Volumes oder Stacks löschen und keine bestehenden
Workloads verändern.
