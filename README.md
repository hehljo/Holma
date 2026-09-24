<div align="center">

<img src="frontend/public/logo-mark.png" alt="" width="120" />

# Holma

### Automated Multi-Source Backup Manager

[![Docker build](https://github.com/hehljo/Holma/actions/workflows/docker-build.yml/badge.svg?branch=main)](https://github.com/hehljo/Holma/actions/workflows/docker-build.yml)
[![License](https://img.shields.io/github/license/hehljo/Holma)](LICENSE)

**[Features](#-features)** • **[Quick Start](#-quick-start)** • **[Documentation](docs/)** • **[API Docs](#-api-documentation)** • **[Contributing](CONTRIBUTING.md)**

---

A self-hosted backup manager with a modern web UI for 35 standard source types including NAS, Git, databases, cloud storage, Docker and Supabase. Runs on ARM64 and AMD64 Docker hosts, including Synology NAS.

> 🌍 Web UI available in **English** and **German**.

</div>

---

## 🗣️ Why "Holma"?

In Augsburg, nobody says *"Could you please go and fetch that?"*. They say **"Hol ma!"** — short for *"hol mal"* / *"holen wir"*: *go get it*, or *let's go get it*. One word, no fuss, and it gets done.

That is the whole job description. Holma goes out to your NAS, your GitHub repositories, your Supabase projects, your databases and your cloud drives, **fetches everything home**, and puts it on the shelf with a date on it — three versions deep, oldest one out when a new one comes in.

It does not ask twice, and it does not bring back half the fridge. Passt scho.

---

## 📋 Table of Contents

<details open>
<summary>Click to expand</summary>

- [Requirements](#-requirements)
- [Quick Start](#-quick-start)
- [Installation](#-installation)
  - [Synology NAS / Portainer](#-synology-nas--portainer)
  - [Linux Server / VPS](#-linux-server--vps)
  - [Raspberry Pi](#-raspberry-pi)
  - [Docker (generic)](#-docker-generic)
  - [Initial Configuration](#initial-configuration)
  - [Data Persistence](#-data-persistence-docker-volumes)
- [Features](#-features)
- [How backups are stored](#-how-backups-are-stored)
- [Test Status](#-test-status)
- [Recent Fixes](#-recent-fixes)
- [Configuration](#️-configuration)
  - [Backup Sources](#backup-sources)
  - [USB Auto-Trigger](#usb-auto-trigger)
  - [Credentials Management](#credentials-management)
- [Usage](#-usage)
  - [Web Interface](#web-interface)
  - [API Usage](#api-usage)
  - [Useful container commands](#useful-container-commands)
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

## 🚀 Quick Start

> [!NOTE]
> Requires Docker 20.10+ and 2 GB+ RAM. Runs on Raspberry Pi, Synology NAS, Linux servers, or any Docker host.

### One-line install

```bash
curl -fsSL https://raw.githubusercontent.com/hehljo/Holma/main/install.sh | bash
```

The installer creates a persistent `.env` file and generates the required `SECRET_KEY` for you.

### Manual setup

> [!IMPORTANT]
> **Every installation requires a `SECRET_KEY` of at least 32 characters.** Keep it persistent and unchanged across restarts, updates and restores. It secures authentication and encrypts stored credentials.

```bash
# 1. Clone the repository
git clone https://github.com/hehljo/Holma.git
cd Holma

# 2. Create a persistent environment file
cp config/example.env .env
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
nano .env  # Set SECRET_KEY to the generated value

# 3. Start the services
docker compose up -d

# 4. Open the Web UI on your trusted local network and create the first account
open http://localhost:3000
```

**First login:** choose your own username and enter a strong password twice in the Web UI. No default account or password is created. Keep the app accessible only to your trusted local network during initial setup: the first visitor can claim the owner account while the database is empty. Existing installations keep their accounts. All source credentials are managed via the Web UI.

---

## 🚀 Installation

> [!WARNING]
> **Deploying a repository stack through Portainer? Select `docker-compose.portainer.yml` explicitly.** Portainer may prefill `docker-compose.yml`; replace it before deploying. The regular file builds images locally and uses different default ports and volume paths. The Portainer file pulls the prebuilt GHCR images and provides the Portainer-specific defaults.

> [!TIP]
> Holma detects your hardware automatically and adjusts resources (workers, RAM limits, parallel tasks) on its own.

### 📦 Synology NAS / Portainer

<details>
<summary>Step-by-step guide</summary>

#### 1. Create folders on the Diskstation (SSH)

```bash
sudo mkdir -p /volume1/docker/holma/{config,data,logs,backup}
```

#### 2. Generate the required SECRET_KEY

> [!IMPORTANT]
> Every Holma installation requires this key. Store it securely and keep it unchanged across updates and restores; without it the backend will not start, and changing it makes stored credentials unreadable.

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

#### 3. Create the stack in Portainer

**Portainer** → **Stacks** → **Add Stack**:

| Field | Value |
|-------|-------|
| **Name** | `holma` |
| **Build method** | Repository |
| **Repository URL** | `https://github.com/hehljo/Holma` |
| **Repository reference** | `refs/heads/main` |
| **Compose path** | `docker-compose.portainer.yml` |

> [!CAUTION]
> Before deploying, verify the Compose path is exactly `docker-compose.portainer.yml`—not Portainer's prefilled `docker-compose.yml`. The latter triggers a local image build and uses different port and volume defaults.

> **Private repo?** → enable **Authentication** → username: your GitHub user → password: Personal Access Token (classic, scope: `repo`)

**Environment variables** (advanced mode):

```
SECRET_KEY=your_generated_key
PLATFORM_PROFILE=auto
API_PORT=5050
FRONTEND_PORT=3080
```

> **Important:** `SECRET_KEY` is mandatory. Portainer does not automatically load a `.env` file from the repository, so add this key as a stack environment variable in Portainer. `PLATFORM_PROFILE`, `API_PORT` and `FRONTEND_PORT` are optional; Compose defaults apply when they are omitted.
>
> The `.env` file itself is not needed for this Portainer setup, but the `SECRET_KEY` normally stored in it is. Store the key securely and keep it unchanged across updates and restores; otherwise, saved credentials can no longer be decrypted. Add other credentials (GitHub, Supabase, etc.) later in the Web UI.

→ **Deploy the stack**

#### 4. Log in

```
http://diskstation-ip:3080
```

**First-time setup:** choose your own username and enter a strong password twice in the Web UI. No default `admin` password exists. Keep the app on your trusted local network until the first account is created: whoever visits first can claim the owner account while the database is empty. Do not expose an uninitialized installation to the internet or untrusted VPN users.

**Existing installations:** persisted accounts remain unchanged; the setup form is unavailable once an account exists. If the password is lost, open the backend container console and run `python -m app.account_cli list-users`, then `python -m app.account_cli reset-password YOUR_USERNAME`. The new password is entered interactively and previous login/automation tokens are revoked. No email server or internet access is required. Do not delete the data volume to reset an account.

#### 5. Configure

1. **Settings → Credentials** → enter GitHub token, NAS passwords etc. (stored encrypted)
2. **Sources → Add Source** → configure backup sources
3. **Start backup** → Dashboard → Start Backup

#### Updates

In **Portainer** → stack `holma` → **Update the stack** → **Re-pull image and redeploy**

#### Synology notes

- **Ports:** DSM occupies 5000/5001 — use `API_PORT=5050` and `FRONTEND_PORT=3080`
- **Autostart after reboot:** handled automatically via `restart: unless-stopped`
- **Permissions:** if you hit permission errors, run `sudo chown -R 1000:1000 /volume1/docker/holma/`
- **Persistent data:** everything under `/volume1/docker/holma/` survives updates

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

#### 2. Install Holma

```bash
cd /opt
sudo git clone https://github.com/hehljo/Holma.git
sudo chown -R $USER:$USER Holma
cd Holma

cp config/example.env .env
cp config/sources-example.json config/sources.json
```

#### 3. Configure

> [!IMPORTANT]
> `SECRET_KEY` is required for this installation. Put the generated value in `.env` and keep it unchanged across updates and restores.

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

#### 2. Install Holma

```bash
cd /opt
sudo git clone https://github.com/hehljo/Holma.git
sudo chown -R pi:pi Holma
cd Holma

cp config/example.env .env
cp config/sources-example.json config/sources.json
```

#### 3. Configure

> [!IMPORTANT]
> `SECRET_KEY` is required for this installation. Put the generated value in `.env` and keep it unchanged across updates and restores.

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

> [!IMPORTANT]
> `SECRET_KEY` is mandatory for this installation as well. Generic Docker Compose deployments normally provide it in `.env`. Keep the same value for the lifetime of the installation; changing it makes stored credentials unreadable.

```bash
git clone https://github.com/hehljo/Holma.git
cd Holma
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

> [!CAUTION]
> Set the Compose path to `docker-compose.portainer.yml`. Do not leave Portainer's `docker-compose.yml` default selected; it builds locally and has different port and volume defaults.

In Portainer → Stacks → Add Stack → Repository:
1. Repository URL: `https://github.com/hehljo/Holma`
2. Compose path: `docker-compose.portainer.yml` (uses prebuilt GHCR images, no build needed)
3. Under **Environment variables**, set a persistent, randomly generated `SECRET_KEY` (at least 32 characters). Portainer does not automatically load the repository's `.env` file.
4. Optionally set `API_PORT`, `FRONTEND_PORT` or other supported overrides; otherwise Compose defaults apply.
5. Deploy

The `.env` file itself is optional for this Portainer method; `SECRET_KEY` is not. Keep the same key across redeployments and restores.

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

**First login:** on a trusted local network, choose a username and enter the password twice in the Web UI. Existing accounts remain valid. For offline recovery, use `docker compose exec backend python -m app.account_cli list-users` and `docker compose exec -it backend python -m app.account_cli reset-password YOUR_USERNAME`.

### 💾 Data Persistence (Docker Volumes)

> [!NOTE]
> **All your data survives a reinstall!**

Holma uses Docker volumes for persistent storage. During updates or reinstalls, the following data is preserved automatically:

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
# Save Holma configuration
cd /opt/Holma
tar -czf holma-config-$(date +%Y%m%d).tar.gz config/ data/ .env

# Copy to a safe location
cp holma-config-*.tar.gz /mnt/external-drive/
```

**Restore after a fresh install:**

```bash
# Fresh install
cd /opt
git clone https://github.com/hehljo/Holma.git
cd Holma

# Restore the backup
tar -xzf /mnt/external-drive/holma-config-*.tar.gz

# Start the containers - all settings are back!
docker compose up -d
```

**Export/Import via the Web UI:**

Since v1.1 you can also export/import all settings directly from the web interface:

1. **Settings** → **Configuration Export/Import**
2. **Export** → downloads a JSON file with all sources & settings
3. **Import** → select a JSON file and restore your configuration

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

### 🗂️ How backups are stored

```
/mnt/backup/<source-id>/
  <source-id>_20260923_020000.tar.gz   <- small sources: one archive per run
  <source-id>_20260924_020000.tar.gz      (GitHub: one repo archive per repository inside)
  _mirrors/                            <- Git working copies, only new commits are fetched

/mnt/backup/<nas-source>/
  <nas-source>_20260923_020000/        <- large sources: snapshot folder per run,
  <nas-source>_20260924_020000/           unchanged files are hard links
  _current/                            <- incremental sync target
```

Retention keeps the newest *N* versions per source (Settings → Storage, default 3). Working folders (`_mirrors`, `_current`) are never rotated.

## 🧪 Test Status

> `✅ Live` bezeichnet einen echten Zielsystemtest. `✅ Auto` bezeichnet grüne Unit-/Fehlerpfad-/Image-Tests; der reale Zielsystemtest ist dort noch offen. `🔲` ist noch nicht belastbar geprüft.
>
> Historische Live-Ergebnisse wurden noch nicht gegen den aktuellen Remediation-Build wiederholt. Aktuelle Details stehen in `docs/SECURITY_AUDIT_LOCAL.md`.
>
> Lokaler Gesamtgate (23.09.2026): `scripts/run-gates.sh` — 8 Backend-Gates, Marken-/Versions-Gate, Frontend-Lint und Produktionsbuild grün. Läuft in CI vor jedem Image-Build.

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

If you've tested a source, please [share your setup](https://github.com/hehljo/Holma/discussions) — it helps others a lot.

---

## 🛠️ Recent Fixes

- **Safe Cloud Copies:** rclone sources now use non-deleting `copy`; source-side removals no longer delete files from the backup destination.
- **Reliable Container Startup:** database initialization is serialized across Gunicorn workers and the backup worker; first-run owner setup is allowed only while no account exists.
- **Automation Tokens:** USB/systemd jobs can use password-bound tokens that expire after at most 365 days and are revoked by password changes.
- **Adaptive UI:** The web UI now has consistent touch targets, visible focus states, responsive page shells, mobile-friendly drawers, bottom-sheet modals, and safer wrapping for backup/source lists.
- **One Archive per Run:** Every backup run becomes exactly one timestamped version per source, and the newest **3** are kept by default (configurable). Small sources (GitHub, GitLab, Gitea, databases, Supabase, Docker, self-hosted apps) become one `.tar.gz` per run with one archive per repository inside. Large file sources (NFS, rsync, rclone, FTP/SFTP, WebDAV, local folders) become snapshot folders where unchanged files are hard links, so three versions of a 100 GB share cost 100 GB plus the changes. NAS via SMB and Proxmox dumps are already one full archive per run and are stored as-is in a timestamped folder (no second compression) — with SMB, each version is a full copy. Failed runs never replace a good version.
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

## ⚙️ Configuration

### Backup Sources

Holma exposes 35 source types supported by the standard image and web form. Configure them in `config/sources.json` or through the web UI:

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

**Storage restore:** enable "Storage-Objekte wiederherstellen" and provide a target Supabase profile or service role key. Holma recreates missing buckets, uploads objects with upsert, and marks the restore as partial if individual Storage uploads fail. Older backups with legacy `_bucket_meta.json` bucket metadata remain supported.

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
docker exec -it holma-backend rclone config
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
sudo systemctl start holma-backup@sda1
journalctl -u 'holma-backup@*' -n 50
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
  -d '{"username": "your_username", "password": "your_password"}' \
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
docker exec holma-backend rclone version
docker exec holma-backend smbclient --version
```

---

## 🌍 Internationalization (i18n)

Holma ships with full multi-language support:

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

All application endpoints except login, first-run setup/status and health checks require a Bearer token
authentication. Login tokens are valid for 24 hours.

```bash
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "your_username",
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

If Portainer reports that `holma-backend` is unhealthy, first check that the stack has a non-empty `SECRET_KEY` environment variable. The backend refuses to start without it, and Portainer does not automatically load `.env` from the Git repository. Keep the same key after the first successful deployment.

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
journalctl -u holma-backup@sd* -n 50 -f

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
docker exec holma-backend smbclient -L //192.168.1.100 -U backup_user

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
ssh-keygen -t ed25519 -o -a 100 -f ~/.ssh/holma

# Copy the public key to the Raspberry Pi
ssh-copy-id -i ~/.ssh/holma.pub pi@raspberrypi.local

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
Holma/
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
docker run --rm --entrypoint python holma/backend:latest \
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

[![GitHub Issues](https://img.shields.io/github/issues/hehljo/Holma?style=for-the-badge)](https://github.com/hehljo/Holma/issues)
[![GitHub Discussions](https://img.shields.io/github/discussions/hehljo/Holma?style=for-the-badge)](https://github.com/hehljo/Holma/discussions)

[Report Bug](https://github.com/hehljo/Holma/issues/new?template=bug_report.md) • [Request Feature](https://github.com/hehljo/Holma/issues/new?template=feature_request.md) • [Ask a Question](https://github.com/hehljo/Holma/discussions)

---

### ☕ Support this project

If Holma helps you manage your backups, consider supporting development!

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-Support%20Development-yellow?style=for-the-badge&logo=buy-me-a-coffee&logoColor=white)](https://buymeacoffee.com/pommesbude)

Your support keeps this project alive and growing! 🙏

</div>

### Resources

- 📚 **[Full documentation](docs/)**
- 🌐 **[i18n guide](docs/i18n.md)**
- 🔐 **[Security policy](SECURITY.md)**

---

<div align="center">

**Made with ❤️ by the Holma community**

⭐ **Star this repo if Holma helps you!** ⭐

[🏠 Home](https://github.com/hehljo/Holma) • [📖 Docs](docs/) • [🐛 Issues](https://github.com/hehljo/Holma/issues) • [💬 Discussions](https://github.com/hehljo/Holma/discussions)

</div>
