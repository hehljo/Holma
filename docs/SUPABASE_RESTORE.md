# Supabase Wiederherstellung - Schritt für Schritt

Diese Anleitung beschreibt, wie du ein Holma-Supabase-Backup in ein neues (oder bestehendes) Supabase-Projekt wiederherstellst.

---

## Voraussetzungen

- **psql** installiert (PostgreSQL Client, mindestens Version 15)
  - macOS: `brew install libpq && brew link --force libpq`
  - Ubuntu/Debian: `sudo apt install postgresql-client`
  - Windows: Im PostgreSQL-Installer den Client mitinstallieren
- **Neues Supabase-Projekt** erstellt (oder ein bestehendes, das überschrieben werden darf)
- Zugriff auf die Backup-Dateien (`roles_*.sql`, `schema_*.sql`, `data_*.sql`)
- Falls Storage gesichert wurde: die `storage/`-Verzeichnisstruktur aus dem Backup

---

## Schritt 1: Neues Projekt vorbereiten

1. Erstelle ein neues Projekt unter [app.supabase.com](https://app.supabase.com)
2. Wähle ein sicheres Datenbankpasswort und speichere es
3. Warte bis das Projekt vollständig initialisiert ist (ca. 2 Minuten)
4. Hole dir den **Connection String**:
   - Gehe zu **Project Settings** → **Database** → **Connection string** → **URI**
   - Der String sieht so aus:
     ```
     postgresql://postgres.[PROJEKT-REF]:[PASSWORT]@aws-0-[REGION].pooler.supabase.com:5432/postgres
     ```
   - **Wichtig:** Verwende den **Session Mode** Pooler (Port 5432), nicht den Transaction Mode

---

## Schritt 2: Backup entpacken

Falls das Backup komprimiert wurde:

```bash
tar xzf supabase_PROJEKTREF_20260318_120000.tar.gz
cd supabase_20260318_120000/
```

Du solltest folgende Dateien sehen:
- `roles_*.sql` - Datenbankrollen
- `schema_*.sql` - Tabellenstruktur, Indizes, Funktionen
- `data_*.sql` - Die eigentlichen Daten
- `storage/` - Storage-Dateien (nur bei Full Backup)
- `config/` - Auth/RLS Config (nur bei Full Backup)

---

## Schritt 3: Datenbank wiederherstellen

**Wichtig:** Führe die Schritte in genau dieser Reihenfolge aus!

Setze zuerst die Connection-Variable:

```bash
export CONNECTION_STRING="postgresql://postgres.[PROJEKT-REF]:[PASSWORT]@aws-0-[REGION].pooler.supabase.com:5432/postgres"
```

### 3.1 Rollen einspielen

```bash
psql --single-transaction \
     --variable ON_ERROR_STOP=1 \
     --file roles_*.sql \
     --dbname "$CONNECTION_STRING"
```

**Hinweis:** Es kann Fehler geben bei Rollen die bereits existieren (z.B. `postgres`, `anon`, `authenticated`). Das ist normal - diese Rollen sind im neuen Projekt schon vorhanden.

Falls Fehler auftreten, entferne `ON_ERROR_STOP=1` und lass die Rollen durchlaufen:

```bash
psql --single-transaction \
     --file roles_*.sql \
     --dbname "$CONNECTION_STRING"
```

### 3.2 Schema einspielen

```bash
psql --single-transaction \
     --variable ON_ERROR_STOP=1 \
     --file schema_*.sql \
     --dbname "$CONNECTION_STRING"
```

**Häufiges Problem:** Falls Fehler mit `supabase_admin` als Owner auftreten:

```bash
# Zeilen mit supabase_admin Owner entfernen/auskommentieren
sed -i 's/OWNER TO supabase_admin/OWNER TO postgres/g' schema_*.sql
# Dann erneut versuchen
```

### 3.3 Daten einspielen

Die Daten müssen mit deaktivierter Replikation eingespielt werden, damit Trigger nicht feuern:

```bash
psql --single-transaction \
     --variable ON_ERROR_STOP=1 \
     --command 'SET session_replication_role = replica' \
     --file data_*.sql \
     --dbname "$CONNECTION_STRING"
```

**Alternativ als ein Befehl (wie von Supabase empfohlen):**

```bash
psql \
  --single-transaction \
  --variable ON_ERROR_STOP=1 \
  --file roles_*.sql \
  --file schema_*.sql \
  --command 'SET session_replication_role = replica' \
  --file data_*.sql \
  --dbname "$CONNECTION_STRING"
```

---

## Schritt 4: Storage wiederherstellen

Storage-Objekte können nicht per SQL wiederhergestellt werden. Sie müssen über die Supabase API oder das Dashboard hochgeladen werden.

### 4.1 Buckets erstellen

Gehe ins Supabase Dashboard → **Storage** und erstelle die Buckets aus dem Backup.
Die Bucket-Konfiguration findest du in `storage/[bucket-name]/_bucket_meta.json`.

### 4.2 Dateien hochladen

**Option A: Über das Dashboard**
- Navigiere zu jedem Bucket und lade die Dateien manuell hoch

**Option B: Per Script mit der Supabase JS Library**

```bash
npm install @supabase/supabase-js
```

```javascript
const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');
const path = require('path');

const supabase = createClient(
  'https://[PROJEKT-REF].supabase.co',
  '[SERVICE_ROLE_KEY]'
);

async function uploadDir(bucketName, localDir, prefix = '') {
  const entries = fs.readdirSync(localDir, { withFileTypes: true });

  for (const entry of entries) {
    if (entry.name.startsWith('_')) continue; // Skip metadata files

    const localPath = path.join(localDir, entry.name);
    const remotePath = prefix ? `${prefix}/${entry.name}` : entry.name;

    if (entry.isDirectory()) {
      await uploadDir(bucketName, localPath, remotePath);
    } else {
      const fileBuffer = fs.readFileSync(localPath);
      const { error } = await supabase.storage
        .from(bucketName)
        .upload(remotePath, fileBuffer, { upsert: true });

      if (error) {
        console.error(`Fehler bei ${remotePath}:`, error.message);
      } else {
        console.log(`Hochgeladen: ${bucketName}/${remotePath}`);
      }
    }
  }
}

// Alle Buckets durchgehen
const storageDir = './storage';
const buckets = fs.readdirSync(storageDir, { withFileTypes: true })
  .filter(d => d.isDirectory());

(async () => {
  for (const bucket of buckets) {
    console.log(`Bucket: ${bucket.name}`);
    await uploadDir(bucket.name, path.join(storageDir, bucket.name));
  }
  console.log('Storage-Restore abgeschlossen.');
})();
```

---

## Schritt 5: Nacharbeiten

Nach der Wiederherstellung müssen einige Dinge manuell konfiguriert werden:

### 5.1 Webhooks aktivieren

- Dashboard → **Database** → **Webhooks**
- Webhooks müssen im neuen Projekt neu erstellt werden
- Die Webhook-URLs und Secrets aus dem alten Projekt verwenden

### 5.2 Realtime-Publications rekonfigurieren

- Dashboard → **Database** → **Replication**
- Die Tabellen für Realtime-Subscriptions neu aktivieren
- Prüfe welche Tabellen im alten Projekt Realtime aktiviert hatten

### 5.3 Extensions aktivieren

- Dashboard → **Database** → **Extensions**
- Aktiviere alle Extensions die im alten Projekt aktiv waren
- Häufig verwendete: `pgvector`, `pg_cron`, `pgjwt`, `uuid-ossp`

### 5.4 Custom Rollen: Passwörter neu setzen

Falls du eigene Datenbankrollen verwendest:

```sql
ALTER ROLE meine_custom_rolle WITH PASSWORD 'neues_sicheres_passwort';
```

### 5.5 Edge Functions

Edge Functions werden nicht per Datenbank-Backup gesichert. Falls du Edge Functions verwendest, müssen diese separat deployed werden (z.B. aus deinem Git-Repository).

### 5.6 Auth-Provider

- Dashboard → **Authentication** → **Providers**
- OAuth-Provider (Google, GitHub, etc.) müssen im neuen Projekt neu konfiguriert werden
- Client-IDs und Secrets aus dem alten Projekt übernehmen

---

## Troubleshooting

### "permission denied for schema"

```bash
# Dem postgres-User alle Rechte geben
psql --dbname "$CONNECTION_STRING" -c "GRANT ALL ON SCHEMA public TO postgres;"
```

### "relation already exists"

Die Tabelle existiert bereits im neuen Projekt. Entweder:
- Das Schema vorher droppen: `DROP SCHEMA public CASCADE; CREATE SCHEMA public;`
- Oder ein komplett neues Projekt erstellen

### "role 'supabase_admin' does not exist"

Im Schema-Dump Owner-Referenzen ersetzen:
```bash
sed -i 's/supabase_admin/postgres/g' schema_*.sql
```

### "COPY failed: relation does not exist"

Das Schema wurde nicht korrekt eingespielt. Prüfe ob Schritt 3.2 fehlerfrei durchgelaufen ist.

### "SSL connection required"

Falls der Connection String keine SSL-Verbindung aufbaut:
```bash
export CONNECTION_STRING="postgresql://postgres.[PROJEKT-REF]:[PASSWORT]@aws-0-[REGION].pooler.supabase.com:5432/postgres?sslmode=require"
```

### Timeout bei großen Datenbanken

Bei großen Dumps den Statement-Timeout erhöhen:
```bash
psql --dbname "$CONNECTION_STRING" -c "SET statement_timeout = '0';" --file data_*.sql
```

### "duplicate key value violates unique constraint"

Tritt auf wenn Daten im neuen Projekt bereits existieren. Lösung:
```sql
-- Alle Tabellen im public Schema leeren
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
        EXECUTE 'TRUNCATE TABLE public.' || quote_ident(r.tablename) || ' CASCADE';
    END LOOP;
END $$;
```

---

## Automatischer Restore

Holma erstellt ausschließlich Backups. Die Wiederherstellung erfolgt **bewusst manuell**, da:

1. **Sicherheit:** Ein automatischer Restore könnte versehentlich Produktionsdaten überschreiben
2. **Kontrolle:** Bei der Wiederherstellung müssen oft projektspezifische Anpassungen gemacht werden (Owner, Rollen, Extensions)
3. **Verifizierung:** Nach dem Restore sollte manuell geprüft werden ob alles korrekt funktioniert

Für regelmäßige Disaster-Recovery-Tests empfehlen wir, diese Anleitung in einem Testprojekt durchzuspielen.
