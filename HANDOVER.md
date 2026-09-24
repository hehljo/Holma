# Handover — 24.09.2026

## Zuletzt beendet
- Erst-Setup akzeptiert beliebige nichtleere Unicode-Passwörter; Bestätigung vergleicht UTF-8-Bytes ohne HTTP 500 bei `ß`. Anmeldung, Änderung, Registrierung und Offline-Reset decken Unicode und kurze Passwörter ab.
- UI-Regeln DE/EN und README auf die bewusst freie Passwortwahl abgestimmt. Kein Eingriff in die DiskStation-Datenbank.
- Lokale Gates: 83 Backend-Tests, Frontend-Lint/-Build und Ruttla ohne blockierende Befunde. Parallel wurde ein allgemeiner Python-Check in `/root/Ruttla` ergänzt.

## Exakter Startpunkt der nächsten Session
- CI für den letzten `main`-Push prüfen. Nach grünen AMD64-/ARM64-Images auf der DiskStation BEIDE `latest`-Images neu ziehen und Container neu erstellen, ohne Daten-Volume anzufassen.
- Im Browser die Ersteinrichtung mit `ß` testen: Konto anlegen, anmelden und Passwort später ändern. Bei Fehler nur HTTP-Status und Backend-Traceback prüfen, niemals das Passwort protokollieren.
