<div align="center">

<img src="icon/README-Logo.png" alt="BackupGenie" width="560" />

### Automated Multi-Source Backup Manager

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/Docker-20.10%2B-blue.svg)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/Node.js-20.19%2B-green.svg)](https://nodejs.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-support-yellow.svg?logo=buy-me-a-coffee&logoColor=white)](https://buymeacoffee.com/pommesbude)

**[Features](#-features)** • **[Quick Start](#-quick-start)** • **[Documentation](docs/)** • **[API Docs](#-api-documentation)** • **[Contributing](CONTRIBUTING.md)**

---

A self-hosted backup manager with a modern web UI for 35 standard source types including NAS, Git, databases, cloud storage, Docker and Supabase. Runs on ARM64 and AMD64 Docker hosts, including Synology NAS.

> 🌍 Web UI available in **English** and **German**.

</div>

---

## 🧪 Test Status

> `✅ Live` bezeichnet einen echten Zielsystemtest. `✅ Auto` bezeichnet grüne Unit-/Fehlerpfad-/Image-Tests; der reale Zielsystemtest ist dort noch offen. `🔲` ist noch nicht belastbar geprüft.
>
> Historische Live-Ergebnisse wurden noch nicht gegen den aktuellen Remediation-Build wiederholt. Aktuelle Details stehen in `docs/SECURITY_AUDIT_LOCAL.md`.
>
> Lokaler Gesamtgate (01.09.2026): 60/60 Backend-Tests, Frontend-Lint und Produktionsbuild grün; npm/pip ohne bekannte Schwachstellen, Bandit ohne hohe oder mittlere Funde.

| Source | Backup | Restore | Notes |
|--------|--------|---------|-------|
| **GitHub** (mirror clone, auto-discovery) | ✅ Live (Altstand) | — | im vollständigen Backend-Gate geprüft |
| **Supabase** (DB + Storage + Auth Config) | ✅ Live (Altstand) | ✅ Auto | Restore-Fehlerpfade aktuell geprüft |
| NAS (SMB) | ✅ Auto | — | Dienst live erreichbar, Anmeldung erzwungen; Testfreigabe-E2E offen |
| rsync over SSH | ✅ Auto | — | Command-/Secret-Gate; Live offen |
| GitLab | ✅ Auto | — | gemeinsames Git-Mirror-/Archiv-Gate |
| Bitbucket | ✅ Auto | — | gemeinsames Git-Mirror-/Archiv-Gate |
| Gitea / Forgejo / Codeberg | ✅ Auto | — | sauberer Remote/Auth-Vertrag geprüft |
| MySQL / MariaDB | ✅ Auto | — | Credential-Datei und Image-Client geprüft |
| PostgreSQL | ✅ Auto | ✅ Auto (Supabase) | CLI, Fehlerpfade und Restore-Sicherheit geprüft |
| Redis | ✅ Auto | — | Remote-RDB und Secret-Übergabe geprüft |
| SQLite | ✅ Auto | — | Live-Backup-API plus Integritätscheck geprüft |
| CouchDB | ✅ Auto | — | read-only HTTP-Handler geprüft; Live offen |
| Google Drive (rclone) | ✅ Auto | — | nicht-löschendes `rclone copy` + Image-CLI; Live offen |
| Dropbox (rclone) | ✅ Auto | — | nicht-löschendes `rclone copy` + Image-CLI; Live offen |
| OneDrive (rclone) | ✅ Auto | — | nicht-löschendes `rclone copy` + Image-CLI; Live offen |
| S3 / Backblaze B2 (rclone) | ✅ Auto | — | Secret-/Command-/Image-Gate; Live offen |
| Portainer stack export | ✅ Auto | — | Status-API live auf Port 9000; authentifizierter Export offen |
| Docker Volumes / Images | ✅ Auto | — | Fehler-/Restart-/Image-CLI-Gates; Live offen |
| Home Assistant | 🔲 | — | read-only API-Export |
| Local filesystem | ✅ Auto | — | rsync-Fehlerpfad geprüft; Live offen |

| Host-/Transport-Gate | Status | Notes |
|----------------------|--------|-------|
| Tailscale → `diskstation` | ✅ Live | direkte Verbindung, 17 ms |
| DSM HTTPS (`5001`) | ✅ Live | HTTP 200 |
| Portainer Status (`9000`) | ✅ Live | API erreichbar; `9443` auf dieser NAS geschlossen |
| DiskStation Docker-Engine | 🔲 | SSH-Port geschlossen; read-only API-Zugang noch nötig |

If you've tested a source, please [share your setup](https://github.com/hehljo/BackupGenie/discussions) — it helps others a lot.

---

## 🛠️ Recent Fixes

- **Safe Cloud Copies:** rclone sources now use non-deleting `copy`; source-side removals no longer delete files from the backup destination.
- **Reliable Container Startup:** database/bootstrap initialization is serialized across Gunicorn workers and the backup worker.
- **Automation Tokens:** USB/systemd jobs can use password-bound tokens that expire after at most 365 days and are revoked by password changes.
- **Adaptive UI:** The web UI now has consistent touch targets, visible focus states, responsive page shells, mobile-friendly drawers, bottom-sheet modals, and safer wrapping for backup/source lists.
- **Backup Retention:** Settings now include automatic cleanup plus configurable backup versions per source. Cleanup only removes older timestamp-based artifacts after successful backups; sync/mirror targets are left alone.
- **Source Handler Compatibility:** Non-GitHub/Supabase handlers now accept UI-created list fields, direct credentials, and path fallbacks more robustly across local, database, Docker, FTP/SFTP, WebDAV, rclone, rsync, self-hosted, and Proxmox sources.
- **i18n Cleanup:** The language selector is always visible and common Settings/Storage/Config dialogs now use localized English/German strings.
- **Dark Mode:** The web UI now follows the system theme on first load, keeps manual theme changes, and includes dark-safe colors for forms, cards, modals, badges, logs, and notifications.
- **Supabase Full Backup:** Fixed full-mode backups with Storage/Auth config by resolving the service role key from the selected credential profile.
- **Restore Safety:** Restore paths are now restricted to the configured backup directory and archive extraction is protected against path traversal.
- **GitHub Backups:** Mirror clones no longer store access tokens in remote URLs; failed Git commands are reported as failures instead of successful backups.
- **Configuration Export:** Secret-like values are redacted recursively before exporting configuration files.
- **Source Forms:** UI-created sources now normalize paths, lists, repositories, Docker volumes/images, and NAS/SMB shares for the backend handlers.
- **Notifications:** Notification endpoints require authentication and the UI uses the real configured channels instead of placeholder data.

---

## ✨ Features

<table>
<tr>
<td width="50%">

### 🔄 35 Standard Source Types
- **Network Storage**: NAS (SMB), rsync over SSH, WebDAV
- **Git Platforms**: GitHub (auto-discovery), GitLab, Bitbucket, Gitea
- **BaaS/PaaS**: Supabase (DB + Storage + Config)
- **Databases**: MySQL/MariaDB, PostgreSQL, Redis, SQLite, CouchDB
- **Cloud Storage**: Google Drive, Dropbox, OneDrive, S3
- **API Exports**: Home Assistant, Grafana, Node-RED, Portainer, Syncthing
- **Docker**: volumes and images
- **Local**: filesystems, home directories

📚 [Full source list →](docs/BACKUP_SOURCES.md)

</td>
<td width="50%">

### 🎯 Smart Automation
- ⚡ **USB trigger**: auto-start when a drive is plugged in (Pi)
- 🔍 **Auto-discovery**: detect GitHub repos automatically
- 🌐 **Modern Web UI**: React-based SPA
- 🔐 **Secure**: SSH key auth, SSL/TLS, RBAC
- 📊 **Real-time monitoring**: live dashboard & logs
- 🐳 **Docker-based**: one-command deployment
- 🖥️ **Universal**: Raspberry Pi, Synology, Linux, Docker
- 🌍 **Multi-language**: 🇬🇧 English & 🇩🇪 German

</td>
</tr>
</table>

---

## 🚀 Quick Start

> [!NOTE]
> Requires Docker 20.10+ and 2 GB+ RAM. Runs on Raspberry Pi, Synology NAS, Linux servers, or any Docker host.

### One-line install

```bash
curl -fsSL https://raw.githubusercontent.com/hehljo/BackupGenie/main/install.sh | bash
```

### Manual setup

```bash
# 1. Clone the repository
git clone https://github.com/hehljo/BackupGenie.git
cd BackupGenie

# 2. Set SECRET_KEY (mandatory)
export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# 3. Start the services
SECRET_KEY=$SECRET_KEY docker compose up -d

# 4. Get the admin password from logs
docker compose logs backend | grep "INIT"

# 5. Open the Web UI → configure credentials and sources
open http://localhost:3000
```

**Login**: `admin` / password from the container logs (step 4). All credentials (tokens, passwords) are managed via the Web UI.

---

## 📋 Table of Contents

<details open>
<summary>Click to expand</summary>

- [Requirements](#-requirements)
- [Installation](#-installation)
  - [Synology NAS / Portainer](#-synology-nas--portainer)
  - [Linux Server / VPS](#-linux-server--vps)
  - [Raspberry Pi](#-raspberry-pi)
  - [Docker (generic)](#-docker-generic)
  - [Initial Configuration](#initial-configuration)
- [Configuration](#️-configuration)
  - [Backup Sources](#backup-sources)
  - [USB Auto-Trigger](#usb-auto-trigger)
  - [Credentials Management](#credentials-management)
- [Usage](#-usage)
  - [Web Interface](#web-interface)
  - [API Usage](#api-usage)
  - [CLI Commands](#cli-commands)
- [Internationalization (i18n)](#-internationalization-i18n)
- [API Documentation](#-api-documentation)
- [Troubleshooting](#-troubleshooting)
- [Security](#-security)
- [Development](#-development)
- [Contributing](#-contributing)
- [License](#-license)

</details>

---

## 🔧 Requirements

### Hardware
| Platform | RAM | Architecture |
|----------|-----|--------------|
| **Raspberry Pi 3/4/5** | 2 GB+ | ARM64 (64-bit OS) |
| **Synology NAS** | 2 GB+ | x86_64/ARM64 |
| **Linux Server** | 2 GB+ | x86_64/ARM64 |
| **Docker Host** | 2 GB+ | x86_64/ARM64 |

Hardware is detected automatically and resources are tuned to match.

### Software
```
Docker:  20.10+
Compose: 2.0+
```

### Authentication Requirements
- 🔑 **NAS**: SMB credentials
- 🔑 **GitHub**: Personal Access Token
- 🔑 **Cloud**: OAuth2 credentials or API keys
- 🔑 **SSH**: private key for rsync

---

## 🚀 Installation

> [!TIP]
> BackupGenie detects your hardware automatically and adjusts resources (workers, RAM limits, parallel tasks) on its own.

### 📦 Synology NAS / Portainer

<details>
<summary>Step-by-step guide</summary>

#### 1. Create folders on the Diskstation (SSH)

```bash
sudo mkdir -p /volume1/docker/backupgenie/{config,data,logs,backup}
```

#### 2. Generate a SECRET_KEY

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### 3. Create the stack in Portainer

**Portainer** → **Stacks** → **Add Stack**:

| Field | Value |
|-------|-------|
| **Name** | `backupgenie` |
| **Build method** | Repository |
| **Repository URL** | `https://github.com/hehljo/BackupGenie` |
| **Repository reference** | `refs/heads/main` |
| **Compose path** | `docker-compose.portainer.yml` |

> **Private repo?** → enable **Authentication** → username: your GitHub user → password: Personal Access Token (classic, scope: `repo`)

**Environment variables** (advanced mode):

```
SECRET_KEY=your_generated_key
PLATFORM_PROFILE=auto
API_PORT=5050
FRONTEND_PORT=3080
```

> No `.env` file required! Just these four variables. All credentials (GitHub token, Supabase etc.) are managed through the Web UI.

→ **Deploy the stack**

#### 4. Log in

```
http://diskstation-ip:3080
```

**Password:** generated randomly on first start. Find it in Portainer → container `backupgenie-backend` → **Logs** → search for `[INIT] Admin user created. Password:`

Change the password immediately under **Settings → User**.

#### 5. Configure

1. **Settings → Credentials** → enter GitHub token, NAS passwords etc. (stored encrypted)
2. **Sources → Add Source** → configure backup sources
3. **Start backup** → Dashboard → Start Backup

#### Updates

In **Portainer** → stack `backupgenie` → **Update the stack** → **Re-pull image and redeploy**

#### Synology notes

- **Ports:** DSM occupies 5000/5001 — use `API_PORT=5050` and `FRONTEND_PORT=3080`
- **Autostart after reboot:** handled automatically via `restart: unless-stopped`
- **Permissions:** if you hit permission errors, run `sudo chown -R 1000:1000 /volume1/docker/backupgenie/`
- **Persistent data:** everything under `/volume1/docker/backupgenie/` survives updates

</details>

### 🐧 Linux Server / VPS

<details>
<summary>Step-by-step guide</summary>

#### 1. Install Docker (if not already installed)

```bash
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker $USER
# Log in again so the group change takes effect
```

#### 2. Install BackupGenie

```bash
cd /opt
sudo git clone https://github.com/hehljo/BackupGenie.git
sudo chown -R $USER:$USER BackupGenie
cd BackupGenie

cp config/example.env .env
cp config/sources-example.json config/sources.json
```

#### 3. Configure

```bash
# Generate a value, then paste it unchanged into .env
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
nano .env
```
```dotenv
SECRET_KEY=paste_the_generated_value_here
BACKUP_BASE_PATH=/mnt/backups
```

#### 4. Start

```bash
docker compose up -d
docker compose ps
```

#### 5. Open the Web UI

```
http://server-ip:3000
```

</details>

### 🥧 Raspberry Pi

<details>
<summary>Step-by-step guide</summary>

#### 1. Prepare the system

```bash
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker pi

sudo reboot
```

#### 2. Install BackupGenie

```bash
cd /opt
sudo git clone https://github.com/hehljo/BackupGenie.git
sudo chown -R pi:pi BackupGenie
cd BackupGenie

cp config/example.env .env
cp config/sources-example.json config/sources.json
```

#### 3. Configure

```bash
# Generate a value, then paste it unchanged into .env
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
nano .env
```
```dotenv
SECRET_KEY=paste_the_generated_value_here
BACKUP_BASE_PATH=/mnt/backup

# Pi 3 with limited RAM: tune the limits
# BACKEND_MEMORY_LIMIT=512M
# BACKEND_CPU_LIMIT=1.5
# FRONTEND_MEMORY_LIMIT=128M
```

#### 4. Start

```bash
docker compose up -d
```

#### 5. Open the Web UI

```
http://raspberrypi.local:3000
```

#### Set up USB auto-trigger (optional)

Plug in a USB drive → backup starts automatically:

```bash
sudo python3 scripts/create-api-token.py
sudo ./scripts/install-systemd.sh
```

Detailed guide: [USB Auto-Trigger →](#usb-auto-trigger)

</details>

### 🐳 Docker (generic)

<details>
<summary>For any platform with Docker</summary>

```bash
git clone https://github.com/hehljo/BackupGenie.git
cd BackupGenie
cp config/example.env .env
cp config/sources-example.json config/sources.json

# Generate SECRET_KEY, then paste the output into .env
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
nano .env

# Start
docker compose up -d

# Web UI: http://localhost:3000
```

#### Portainer (without Synology)

In Portainer → Stacks → Add Stack → Repository:
1. Repository URL: `https://github.com/hehljo/BackupGenie`
2. Compose path: `docker-compose.portainer.yml` (uses prebuilt GHCR images, no build needed)
3. Set environment variables (at minimum `SECRET_KEY`)
4. Deploy

#### Environment variables for resource tuning

| Variable | Default | Description |
|----------|---------|-------------|
| `PLATFORM_PROFILE` | `auto` | `auto`, `raspberrypi`, `synology`, `server` |
| `BACKEND_CPU_LIMIT` | `2.0` | CPU limit for the backend |
| `BACKEND_MEMORY_LIMIT` | `1G` | RAM limit for the backend |
| `FRONTEND_CPU_LIMIT` | `1.0` | CPU limit for the frontend |
| `FRONTEND_MEMORY_LIMIT` | `256M` | RAM limit for the frontend |
| `MAX_PARALLEL_TASKS` | `auto` | Parallel backup tasks (auto = based on RAM) |

</details>

### Initial Configuration

> [!IMPORTANT]
> `SECRET_KEY` is mandatory. Without it, the app refuses to start.
> Generate one: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`

**Required environment variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Random string for JWT + credential encryption |
| `API_PORT` | No (5000) | Port for the backend API |
| `FRONTEND_PORT` | No (3000) | Port for the Web UI |
| `PLATFORM_PROFILE` | No (auto) | `auto`, `raspberrypi`, `synology`, `server` |

> **Credentials** (GitHub token, NAS passwords, Supabase keys etc.) are **not** set via environment variables — manage them through the Web UI under **Settings → Credentials**. They are stored AES-encrypted in the database.

**Login:** `admin` / password is generated randomly on first start → `docker compose logs backend | grep "INIT"`

### 💾 Data Persistence (Docker Volumes)

> [!NOTE]
> **All your data survives a reinstall!**

BackupGenie uses Docker volumes for persistent storage. During updates or reinstalls, the following data is preserved automatically:

**Persistent directories:**

```yaml
./config/         # ✅ All backup sources (sources.json)
                  # ✅ rclone configuration
                  # ✅ Notification settings

./data/           # ✅ Database (users, history, settings)
                  # ✅ Backup logs
                  # ✅ Metadata

./logs/           # ✅ Application logs

/mnt/backup/      # ✅ Your backup data (configurable)
```

**Benefits:**
- 🔄 **Safe updates:** `docker compose pull && docker compose up -d`
- 💾 **Backup-friendly:** just back up `./config/` and `./data/`
- 🚀 **Migration:** copy folders → fresh install → done!
- ⚡ **Rollback:** start an older container version with no data loss

**Create a full backup:**

```bash
# Save BackupGenie configuration
cd /opt/BackupGenie
tar -czf backupgenie-config-$(date +%Y%m%d).tar.gz config/ data/ .env

# Copy to a safe location
cp backupgenie-config-*.tar.gz /mnt/external-drive/
```

**Restore after a fresh install:**

```bash
# Fresh install
cd /opt
git clone https://github.com/hehljo/BackupGenie.git
cd BackupGenie

# Restore the backup
tar -xzf /mnt/external-drive/backupgenie-config-*.tar.gz

# Start the containers - all settings are back!
docker compose up -d
```

**Export/Import via the Web UI:**

Since v1.1 you can also export/import all settings directly from the web interface:

1. **Settings** → **Configuration Export/Import**
2. **Export** → downloads a JSON file with all sources & settings
3. **Import** → select a JSON file and restore your configuration

---

## ⚙️ Configuration

### Backup Sources

BackupGenie exposes 35 source types supported by the standard image and web form. Configure them in `config/sources.json` or through the web UI:

<details>
<summary>📁 NAS (SMB)</summary>

```json
{
  "id": "nas-project1",
  "name": "NAS - Project 1",
  "type": "nas",
  "enabled": true,
  "priority": 1,
  "config": {
    "host": "192.168.1.100",
    "share": "projects",
    "path": "project1",
    "username": "backup_user",
    "credentials": {
      "password_env": "NAS_PASSWORD"
    },
    "options": {
      "timeout": 3600
    }
  },
  "schedule": {
    "enabled": true,
    "trigger": "cron,usb_mount",
    "frequency": "daily",
    "time": "03:00",
    "max_duration": 3600
  }
}
```

**Read-only connection test:**
```bash
smbclient //192.168.1.100/projects -U backup_user -c ls
```

</details>

<details>
<summary>🐙 GitHub Repositories (auto-discovery)</summary>

```json
{
  "id": "github-repos",
  "name": "GitHub Repositories",
  "type": "github",
  "enabled": true,
  "priority": 2,
  "discovery_mode": "all",
  "exclude": ["user/some-unwanted-fork"],
  "repositories": [],
  "credentials": {
    "token_env": "GITHUB_TOKEN"
  },
  "options": {
    "include_wikis": true,
    "include_lfs": true
  }
}
```

**`discovery_mode`**: `"all"` automatically backs up all repos (private + public + orgs). New repos are picked up on the next backup. Use `"manual"` to pick repos individually via the Web UI.

**Generate a token:** GitHub → Settings → Developer settings → Personal access tokens → scopes: `repo`, `gist`

</details>

<details>
<summary>🟢 Supabase (DB + Storage)</summary>

Configuration is done through the Web UI:

1. **Settings → Credentials → Supabase** → create a new profile with the connection string (Session Pooler URI from the Supabase dashboard) + DB password + optional service role key
2. **Sources → Add Source → Supabase** → pick a profile + choose backup mode (`db_only` or `full`)
3. **Start backup**

**`backup_mode`**: `full` saves DB (roles + schema + data) + storage buckets + RLS/auth config. `db_only` for PostgreSQL dumps only.

**Storage backup:** `full` mode with "Storage Buckets einschließen" downloads all bucket objects into `storage/<bucket>/...` and writes bucket/object metadata to `storage_metadata/`. This preserves image/file content plus common upload metadata such as content type and cache control for restore.

**Restore:** History → backup with the restore button → choose target profile → start restore. Manual connection string entry is also supported.

**Storage restore:** enable "Storage-Objekte wiederherstellen" and provide a target Supabase profile or service role key. BackupGenie recreates missing buckets, uploads objects with upsert, and marks the restore as partial if individual Storage uploads fail. Older backups with legacy `_bucket_meta.json` bucket metadata remain supported.

</details>

<details>
<summary>☁️ Cloud Storage (rclone)</summary>

```json
{
  "id": "google-drive",
  "name": "Google Drive Backup",
  "type": "rclone",
  "remote": "gdrive",
  "path": "/My_Backup",
  "enabled": true,
  "priority": 3,
  "options": {
    "transfers": 4,
    "checkers": 8
  }
}
```

**Configure rclone:**
```bash
docker exec -it backupgenie-backend rclone config
```

The standard form exposes Google Drive, Dropbox, OneDrive, S3, Backblaze B2, iCloud, Box, MEGA and pCloud plus a generic rclone source.

</details>

<details>
<summary>🐳 Docker Volumes</summary>

```json
{
  "id": "docker-volumes",
  "name": "Docker Volumes",
  "type": "docker-volume",
  "enabled": true,
  "priority": 4,
  "volumes": ["volume1", "volume2"],
  "options": {
    "compress": true,
    "stop_containers": false
  }
}
```

</details>

<details>
<summary>💾 Local Directories</summary>

```json
{
  "id": "local-docs",
  "name": "Local Documents",
  "type": "local",
  "enabled": true,
  "priority": 5,
  "sources": [
    "/home/pi/documents",
    "/home/pi/photos"
  ],
  "options": {
    "recursive": true,
    "delete": false,
    "compress": false
  }
}
```

</details>

📚 **[View all 35 standard source types →](docs/BACKUP_SOURCES.md)**

### USB Auto-Trigger

On a systemd-based Linux host, the included scripts can trigger a backup when a
USB drive is connected. This is not used on Synology DSM.

<details>
<summary>Set up udev + systemd</summary>

#### 1. Create a revocable automation token

```bash
sudo python3 scripts/create-api-token.py
```

The helper accepts only HTTPS or a local HTTP API, asks for the admin password
without echoing it, and stores the token with mode `0600`. Automation tokens are
valid for at most 365 days and are revoked immediately when the account password
changes.

If the backend uses a different local port:

```bash
sudo python3 scripts/create-api-token.py \
  --api-url http://127.0.0.1:5050/api/v1
```

#### 2. Install the checked-in udev/systemd units

```bash
sudo ./scripts/install-systemd.sh
```

#### 3. Verify

```bash
sudo systemctl start backupgenie-backup@sda1
journalctl -u 'backupgenie-backup@*' -n 50
```

Replace `sda1` with a dedicated test partition. The trigger mounts the selected
partition at `/mnt/backup`; review that target before the first real run.

</details>

### Credentials Management

All credentials are managed via the Web UI:

1. **Settings** → **Credentials**
2. Enter token / password (GitHub, NAS, Supabase, SMTP, Telegram etc.)
3. **Save Credentials**

Credentials are stored **AES-encrypted** in the database (Fernet/PBKDF2). No plaintext passwords in files or environment variables.

---

## 💾 Usage

### Web Interface

Access the dashboard at:
```
http://raspberrypi.local:3000
http://YOUR_PI_IP:3000
```

**Features:**
- 📊 Real-time backup status dashboard
- 📜 Detailed backup history with logs
- ⚙️ Source management (add/edit/delete)
- 🔐 Credentials configuration
- 📈 Storage usage statistics
- 🔔 Notification settings
- 🌍 Language switcher (EN/DE)

### API Usage

<details>
<summary>Start a backup via API</summary>

```bash
# Get an API token
TOKEN=$(curl -s -X POST http://localhost:5000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "your_password"}' \
  | jq -r '.access_token')

# Start a backup
curl -X POST http://localhost:5000/api/v1/backup/start \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "sources": ["nas-project1", "github-repos"],
    "parallel": 2
  }'
```

</details>

<details>
<summary>Check backup status</summary>

```bash
curl -X GET http://localhost:5000/api/v1/backup/BACKUP_ID \
  -H "Authorization: Bearer $TOKEN"
```

</details>

### Useful container commands

```bash
# Service status and logs
docker compose ps
docker compose logs --tail=100 backend

# Verify tools included in the backend image
docker exec backupgenie-backend rclone version
docker exec backupgenie-backend smbclient --version
```

---

## 🌍 Internationalization (i18n)

BackupGenie ships with full multi-language support:

### Supported languages
- 🇬🇧 **English** — fully translated
- 🇩🇪 **Deutsch** — vollständig übersetzt

### Language selection
- **Frontend**: language switcher in the sidebar header
- **Backend**: auto-detection via the `Accept-Language` header
- **Storage**: preference saved in browser localStorage

### Adding a new language

See the detailed guide: **[i18n Documentation →](docs/i18n.md)**

**Quick steps:**
1. Frontend: create `frontend/src/locales/{lang}/translation.json`
2. Backend: run `pybabel init -d app/translations -l {lang}`
3. Translate the `.po` files
4. Compile: `pybabel compile -d app/translations`

**Technology stack:**
- Frontend: `react-i18next` + `i18next-browser-languagedetector`
- Backend: `Flask-Babel`

---

## 📡 API Documentation

### Authentication

All application endpoints except login and health checks require Bearer token
authentication. Login tokens are valid for 24 hours.

```bash
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "your_password"
}

Response:
{
  "access_token": "eyJhbGc...",
  "token_type": "Bearer",
  "expires_in": 86400,
  "user": {}
}
```

For unattended scripts, an admin can create a password-bound automation token:

```http
POST /api/v1/auth/api-token
Authorization: Bearer LOGIN_TOKEN
Content-Type: application/json

{
  "current_password": "your_password",
  "expires_days": 365
}
```

Changing that account's password revokes both login and automation tokens.

### Endpoints

<details>
<summary>📦 Backup management</summary>

#### Start a backup
```http
POST /api/v1/backup/start
Authorization: Bearer TOKEN

{
  "sources": ["source-id-1", "source-id-2"],
  "parallel": 2
}

Response 202:
{
  "backup_id": "backup-uuid-1234",
  "status": "queued",
  "started_at": "2025-11-13T19:30:00Z",
  "sources": 2,
  "parallel": 2
}
```

#### Get backup status
```http
GET /api/v1/backup/{backup_id}
Authorization: Bearer TOKEN

Response 200:
{
  "backup_id": "backup-uuid-1234",
  "status": "running",
  "progress": 65,
  "started_at": "2025-11-13T19:30:00Z",
  "sources": [...]
}
```

#### List backup history
```http
GET /api/v1/backup/history?limit=20&offset=0
Authorization: Bearer TOKEN

Response 200:
{
  "total": 156,
  "backups": [...]
}
```

</details>

<details>
<summary>🔧 Source management</summary>

#### List sources
```http
GET /api/v1/sources
Authorization: Bearer TOKEN

Response 200:
{
  "sources": [
    {
      "id": "nas-project1",
      "name": "NAS - Project 1",
      "type": "smb",
      "enabled": true
    }
  ]
}
```

#### Add a source
```http
POST /api/v1/sources
Authorization: Bearer TOKEN
Content-Type: application/json

{
  "name": "GitHub Org",
  "type": "github",
  "repositories": ["org/repo1"],
  "credentials": {
    "token_env": "GITHUB_TOKEN"
  },
  "enabled": true
}

Response 201:
{
  "message": "Source created successfully",
  "source": {
    "id": "github-12345678",
    "name": "GitHub Org",
    "type": "github",
    "enabled": true
  }
}
```

#### Update a source
```http
PUT /api/v1/sources/{source_id}
Authorization: Bearer TOKEN
Content-Type: application/json

{
  "enabled": false
}
```

#### Delete a source
```http
DELETE /api/v1/sources/{source_id}
Authorization: Bearer TOKEN
```

</details>

---

## 🐛 Troubleshooting

<details>
<summary>🚫 Docker containers won't start</summary>

```bash
# Check the logs
docker compose logs backend
docker compose logs frontend

# Rebuild the containers
docker compose down
docker compose up -d --build --force-recreate

# Check system resources
free -h
df -h
```

</details>

<details>
<summary>⚠️ Backup doesn't start automatically</summary>

```bash
# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Check systemd logs
journalctl -u backupgenie-backup@sd* -n 50 -f

# Debug USB devices
lsblk
sudo udevadm info --name=/dev/sda1 --attribute-walk
```

</details>

<details>
<summary>🔌 NAS connection fails</summary>

```bash
# Test SMB connection
smbclient -L //192.168.1.100 -U backup_user

# Test from inside Docker
docker exec backupgenie-backend smbclient -L //192.168.1.100 -U backup_user

# Then use Sources → connection test in the Web UI
```

</details>

<details>
<summary>🔑 GitHub token invalid</summary>

```bash
# Verify the token online
curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/user

# Update the token under Settings → Credentials, then test the source again
```

</details>

<details>
<summary>💽 Disk space full</summary>

```bash
# Check available space
df -h /mnt/backup

# Find the largest files
du -sh /mnt/backup/* | sort -rh | head -20

# Review configured retention under Settings → Storage
# Preview the optional host cleanup script without deleting anything
sudo DRY_RUN=true ./scripts/backup-cleanup.sh
```

</details>

---

## 🔒 Security

> [!IMPORTANT]
> Follow security best practices to protect your backup data!

### SSH hardening

<details>
<summary>Set up secure SSH access</summary>

```bash
# Generate an ED25519 key pair (locally)
ssh-keygen -t ed25519 -o -a 100 -f ~/.ssh/backupgenie

# Copy the public key to the Raspberry Pi
ssh-copy-id -i ~/.ssh/backupgenie.pub pi@raspberrypi.local

# Configure the SSH server
sudo nano /etc/ssh/sshd_config
```

**Recommended `sshd_config` settings:**
```
Port 2222  # Non-standard port
PermitRootLogin no
PubkeyAuthentication yes
PasswordAuthentication no
PermitEmptyPasswords no
MaxAuthTries 3
X11Forwarding no
AllowUsers pi
```

```bash
sudo systemctl restart ssh
```

</details>

### Firewall configuration

```bash
# Enable UFW
sudo ufw enable

# Allow SSH (adjust port if changed)
sudo ufw allow 2222/tcp

# Allow API (local network only)
sudo ufw allow from 192.168.1.0/24 to any port 5000

# Allow Web UI (local network only)
sudo ufw allow from 192.168.1.0/24 to any port 3000

# Check status
sudo ufw status
```

### API token management

```bash
# Interactive, password-bound, maximum lifetime 365 days
sudo python3 scripts/create-api-token.py
```

The helper refuses to overwrite an existing token file. Changing the account
password revokes the token. Source and notification credentials are encrypted in
the database; keep the same `SECRET_KEY` when moving or restoring an installation.

---

## 👨‍💻 Development

### Project structure

```
BackupGenie/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── api/              # REST API endpoints
│   │   │   ├── backup.py
│   │   │   ├── sources.py
│   │   │   └── auth.py
│   │   ├── backup/           # Backup engine
│   │   │   ├── executor.py
│   │   │   ├── sources/      # Backup handler implementations
│   │   │   │   ├── smb.py
│   │   │   │   ├── github.py
│   │   │   │   ├── rclone.py
│   │   │   │   └── ...
│   │   │   ├── jobs.py       # Persistent backup queue
│   │   │   └── worker.py     # Dedicated backup worker
│   │   ├── models/
│   │   │   └── backup.py
│   │   ├── translations/     # i18n translations
│   │   └── config.py
│   ├── tests/                 # unittest regression suite
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── components/       # React components
│   │   ├── pages/
│   │   ├── services/         # API client
│   │   └── locales/          # i18n translations
│   ├── package.json
│   └── Dockerfile
├── config/
│   ├── sources.json          # Backup source definitions
│   ├── rclone.conf          # rclone remote configurations
│   └── sources-example.json
├── scripts/
│   ├── create-api-token.py
│   ├── trigger-backup.sh
│   └── backup-cleanup.sh
├── docs/
│   ├── BACKUP_SOURCES.md    # Complete source documentation
│   ├── i18n.md              # Internationalization guide
│   └── SECURITY_AUDIT_LOCAL.md
└── README.md
```

### Local development setup

```bash
# From the project root, run the backend in its supported container
export SECRET_KEY="development-secret-at-least-32-characters"
docker compose up -d --build backend

# Frontend development server proxies /api to localhost:5000
cd frontend
npm ci
npm run dev
```

### Running tests

```bash
# Backend tests with warnings treated as errors
docker run --rm --entrypoint python backupgenie/backend:latest \
  -W error -m unittest discover -s tests -p 'test_*.py'

# Frontend checks
cd frontend
npm ci
npm run lint
npm run build

# Deployment syntax
SECRET_KEY="validation-secret-at-least-32-characters" docker compose config --quiet
```

### Build Docker images

```bash
# Build all services
docker compose build

# Build a specific service
docker compose build backend

# The GitHub workflow publishes linux/amd64 and linux/arm64 images
```

---

## 🤝 Contributing

Contributions are welcome! See the [Contributing Guide](CONTRIBUTING.md) for details.

### How to contribute

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a pull request

### Development guidelines

- Follow [PEP 8](https://pep8.org/) for Python code
- Follow the [Airbnb Style Guide](https://github.com/airbnb/javascript) for JavaScript
- Write tests for new features
- Update documentation when API behavior changes
- Add i18n translations for any new UI strings

---

## 🎯 Roadmap

**Done**
- [x] Notifications (email, Telegram, ntfy, webhooks via Apprise)
- [x] Supabase backup + restore with profile-based credentials
- [x] Encrypted credential storage (Fernet/PBKDF2)
- [x] EN/DE multi-language UI
- [x] Configuration export/import
- [x] Multi-arch Docker images (amd64, arm64)

**In progress / planned**
- [x] Dark/light theme toggle
- [ ] Advanced filtering in backup history
- [x] Backup scheduling (per-source time schedules)
- [ ] Two-factor authentication (2FA)
- [ ] Audit logging
- [ ] Deduplication / incremental backups
- [ ] Restore UI for additional source types (currently Supabase only)
- [ ] Prometheus metrics export
- [ ] OpenAPI 3.0 spec
- [ ] Additional languages (FR, ES, IT)

---

## 📝 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

## 📞 Support & Community

<div align="center">

**Need help? Have questions?**

[![GitHub Issues](https://img.shields.io/github/issues/hehljo/BackupGenie?style=for-the-badge)](https://github.com/hehljo/BackupGenie/issues)
[![GitHub Discussions](https://img.shields.io/github/discussions/hehljo/BackupGenie?style=for-the-badge)](https://github.com/hehljo/BackupGenie/discussions)

[Report Bug](https://github.com/hehljo/BackupGenie/issues/new?template=bug_report.md) • [Request Feature](https://github.com/hehljo/BackupGenie/issues/new?template=feature_request.md) • [Ask a Question](https://github.com/hehljo/BackupGenie/discussions)

---

### ☕ Support this project

If BackupGenie helps you manage your backups, consider supporting development!

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Support%20Development-yellow?style=for-the-badge&logo=buy-me-a-coffee&logoColor=white)](https://buymeacoffee.com/pommesbude)

Your support keeps this project alive and growing! 🙏

</div>

### Resources

- 📚 **[Full documentation](docs/)**
- 🌐 **[i18n guide](docs/i18n.md)**
- 🔐 **[Security policy](SECURITY.md)**

---

<div align="center">

**Made with ❤️ by the BackupGenie community**

⭐ **Star this repo if BackupGenie helps you!** ⭐

[🏠 Home](https://github.com/hehljo/BackupGenie) • [📖 Docs](docs/) • [🐛 Issues](https://github.com/hehljo/BackupGenie/issues) • [💬 Discussions](https://github.com/hehljo/BackupGenie/discussions)

</div>
