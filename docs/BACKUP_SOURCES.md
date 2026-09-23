# Holma – supported backup sources

This document describes the **35 source types exposed by the standard Docker image and web form**. Existing advanced source definitions remain loadable, but they are not advertised as standard support unless the required tools and privileges are supplied separately.

The current validation state is tracked in the test table near the top of [`README.md`](../README.md). Automated tests and real-system tests are deliberately shown separately.

## Standard source matrix

| Category | Source types | Backup output |
|---|---|---|
| Network storage | `nas`, `rsync-ssh`, `webdav` | SMB TAR archive, rsync copy, WebDAV downloads |
| Local storage | `local` | rsync copy |
| Git | `github`, `gitlab`, `gitea`, `forgejo`, `bitbucket`, `codeberg` | mirrors plus configured metadata/releases |
| Databases | `mysql`, `postgresql`, `redis`, `sqlite`, `couchdb` | native dump/snapshot formats |
| Cloud storage | `gdrive`, `onedrive`, `dropbox`, `s3`, `b2`, `icloud`, `box`, `mega`, `pcloud`, `rclone` | rclone copy |
| File transfer | `ftp`, `sftp` | downloaded directory tree |
| Docker | `docker-volume`, `docker-image` | compressed volume TAR or image TAR |
| Read-only API exports | `homeassistant`, `grafana`, `nodered`, `portainer`, `syncthing` | JSON configuration/metadata export |
| Cloud platform | `supabase` | PostgreSQL dump plus Storage files |

Source-specific fields are normally saved below `config` by the web form. The backend also accepts the established top-level form and safely flattens `config` while loading.

## Minimal examples

### Synology/NAS through SMB

`nas` is the web-form type; `smb` remains a compatible alias. SMB uses `smbclient` in userspace and does not require a privileged CIFS mount.

```json
{
  "id": "nas-smb",
  "name": "NAS test share",
  "type": "nas",
  "enabled": true,
  "config": {
    "host": "diskstation",
    "share": "holma-test",
    "path": "optional/subfolder",
    "username": "holma",
    "password": "store through the encrypted settings/UI",
    "options": {
      "encrypt_transport": false,
      "timeout": 3600
    }
  }
}
```

The connection test performs authenticated listing only. A backup reads the share and writes a TAR archive into Holma's backup destination; it does not modify the SMB share. Transport signing is enabled by default. Set `encrypt_transport` when the server supports mandatory SMB encryption.

### Rsync over SSH

```json
{
  "id": "nas-rsync",
  "name": "NAS through SSH",
  "type": "rsync-ssh",
  "enabled": false,
  "config": {
    "host": "diskstation",
    "port": 22,
    "path": "/volume1/holma-test",
    "username": "holma",
    "ssh_key_path": "/run/secrets/holma_ssh_key",
    "options": {
      "delete": false,
      "strict_host_key_checking": true
    }
  }
}
```

Password authentication is supported without putting the password in the process command line. Host-key verification is on by default. Keep `delete` false unless destination mirroring is explicitly intended.

### Database

```json
{
  "id": "postgres-main",
  "name": "PostgreSQL",
  "type": "postgresql",
  "enabled": false,
  "config": {
    "host": "postgres",
    "port": 5432,
    "database": "app",
    "username": "backup_user",
    "password": "store through the encrypted settings/UI"
  }
}
```

The standard image contains clients for MySQL/MariaDB, PostgreSQL, Redis, SQLite and CouchDB. MySQL uses a protected temporary defaults file; PostgreSQL and Redis use process-local credential environments. SQLite uses its online backup API instead of copying a live database file.

### Docker volume or image

```json
{
  "id": "docker-data",
  "name": "Docker volume",
  "type": "docker-volume",
  "enabled": false,
  "config": {
    "volumes": ["myapp_data"],
    "options": {
      "stop_containers": false
    }
  }
}
```

Docker backup requires the host Docker socket. Volume data is mounted read-only into a short-lived helper container. `stop_containers` defaults to false. Image backups use `docker save`. Both are sensitive host-level capabilities and should only be enabled for trusted administrators.

### Portainer read-only export

```json
{
  "id": "portainer",
  "name": "Portainer",
  "type": "portainer",
  "enabled": false,
  "config": {
    "host": "diskstation",
    "port": 9443,
    "https": true,
    "api_key": "store through the encrypted settings/UI",
    "backup_method": "api",
    "options": {
      "verify_ssl": true
    }
  }
}
```

The Portainer handler only uses `GET` requests. It exports stack metadata and readable stack files through `X-API-Key`; it does not deploy, update, stop or delete stacks. TLS certificate verification is enabled by default.

### Supabase

```json
{
  "id": "supabase-project",
  "name": "Supabase",
  "type": "supabase",
  "enabled": false,
  "config": {
    "connection_string": "postgresql://...",
    "service_role_key": "store through the encrypted settings/UI",
    "backup_mode": "full",
    "options": {
      "include_storage": true,
      "include_auth_config": true,
      "compress": true
    }
  }
}
```

Supabase is currently the only source with an integrated restore workflow. A restore is never implied by a successful backup test.

## Credentials and safety

- Enter secrets through the web UI/settings API or environment variables. Do not commit real secrets to JSON files.
- Inline source and notification secrets are encrypted at rest. Keep the same `SECRET_KEY`, or stored encrypted values can no longer be decrypted.
- Connection tests are read-only for the supported implementations.
- Backup roots and source identifiers are validated against path traversal.
- Destructive destination mirroring must be explicitly enabled; examples keep it disabled.

## Advanced compatibility handlers

The backend retains compatibility mappings for types such as `nfs`, `mongodb`, `influxdb` and additional generic self-hosted services. They are intentionally hidden from the standard form because their tools, privileges, configuration contract or restore guarantees are not part of the standard image.

For NFS, mount the export read-only on the Docker host and expose that mounted folder to Holma as a `local` source. Direct NFS mounting inside the container requires a custom privileged deployment and is not the recommended standard setup.

## Restore status

| Source | Integrated restore |
|---|---|
| Supabase | Yes, database and selected Storage content |
| PostgreSQL | Internal restore implementation used by the Supabase workflow |
| All other standard sources | No integrated restore; use the native target tool and the produced artifact |

Always validate restores into a disposable target before relying on a backup for production recovery.
