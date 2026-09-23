"""
Proxmox VE Backup Handler
Best Practice 02/2026: Uses vzdump API for VM/Container backups,
supports both API and CLI modes for maximum flexibility.
Common in homelab setups alongside Raspberry Pi.
"""
import subprocess
import logging
import os
import json
import time
import requests
import re
from app.backup.base import BackupHandler
from app.brand import BRAND_NAME

logger = logging.getLogger(__name__)


class ProxmoxBackup(BackupHandler):
    """
    Proxmox VE backup handler.

    Supports:
    - Full VM/Container backups via vzdump (API or CLI)
    - Configuration-only backups
    - PBS (Proxmox Backup Server) integration

    Methods:
    - 'api': Uses Proxmox REST API (recommended, works remote)
    - 'cli': Uses vzdump CLI directly (must run on PVE host)
    """

    # vzdump output is large and already compressed.
    ARTIFACT_MODE = 'folder'

    def backup(self):
        """Execute Proxmox VE backup"""
        method = self.source_config.get('options', {}).get('method', 'api')

        if method == 'cli':
            return self._backup_cli()
        else:
            return self._backup_api()

    def _backup_api(self):
        """Backup VMs/Containers via Proxmox REST API"""
        host = self.source_config.get('host', '')
        port = self.source_config.get('port', 8006)
        node = self.source_config.get('node', 'pve')
        credentials = self.source_config.get('credentials', {})
        options = self.source_config.get('options', {})

        if not host:
            raise Exception("Proxmox host is required")
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,253}', str(host)):
            raise Exception('Invalid Proxmox host')
        if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', str(node)):
            raise Exception('Invalid Proxmox node')

        # Get API token or user/password
        token_env = credentials.get('token_env', '')
        token_id = self.source_config.get('token_id') or credentials.get('token_id', '')  # e.g., "backup@pam!backup-token"
        api_token = self.source_config.get('token', '')

        if api_token or token_env:
            if not api_token:
                api_token = self._get_env_credential(token_env)
            if not token_id:
                raise Exception('Proxmox token_id is required for API token auth')
            headers = {'Authorization': f'PVEAPIToken={token_id}={api_token}'}
        else:
            # Fallback: user/password auth (get ticket)
            username = self._get_env_credential(credentials.get('username_env', 'PROXMOX_USER'))
            password = self._get_env_credential(credentials.get('password_env', 'PROXMOX_PASSWORD'))
            verify_ssl = options.get('verify_ssl', True)
            headers = self._get_auth_ticket(
                host, port, username, password, verify_ssl
            )

        base_url = f"https://{host}:{port}/api2/json"
        verify_ssl = options.get('verify_ssl', True)

        # Get list of VMs/Containers to backup
        vmids = self._as_list(self.source_config.get('vmids'))  # Explicit list
        backup_all = self.source_config.get('backup_all', False)

        if backup_all:
            vmids = self._list_all_vmids(base_url, node, headers, verify_ssl)
            self.log(f"Found {len(vmids)} VMs/Containers on node {node}")

        if not vmids:
            raise Exception("No VMIDs specified and backup_all is false")

        files_synced = 0
        size_synced = 0

        for vmid in vmids:
            try:
                vmid = str(vmid)
                if not vmid.isdigit():
                    raise Exception('Invalid VMID')
                self.log(f"Starting backup for VMID {vmid}...")

                # Start vzdump via API
                vzdump_options = {
                    'vmid': vmid,
                    'mode': options.get('mode', 'snapshot'),  # snapshot, suspend, stop
                    'compress': options.get('compress', 'zstd'),
                    'remove': 0,  # Don't remove old backups
                    'notes-template': f'{BRAND_NAME} auto-backup {time.strftime("%Y-%m-%d")}',
                }

                # Set storage target
                if options.get('storage'):
                    vzdump_options['storage'] = options['storage']

                resp = requests.post(
                    f"{base_url}/nodes/{node}/vzdump",
                    headers=headers,
                    data=vzdump_options,
                    verify=verify_ssl,
                    timeout=30
                )
                resp.raise_for_status()
                task_id = resp.json().get('data', '')

                if not task_id:
                    raise Exception(f"Proxmox returned no task id for VMID {vmid}")
                # Wait for task completion
                self._wait_for_task(base_url, node, task_id, headers, verify_ssl)

                self.log(f"Backup completed for VMID {vmid}")
                files_synced += 1

                # If config-only backup is also requested
                if options.get('backup_config', True):
                    self._backup_vm_config(base_url, node, vmid, headers, verify_ssl)

            except Exception as e:
                self.log(f"ERROR backing up VMID {vmid}: {str(e)}")
                logger.error(f"Error backing up VMID {vmid}: {e}")

        # Download backup files to local destination if configured
        if options.get('download_backups', True):
            size_synced = self._download_backups(
                base_url, node, vmids, headers, verify_ssl, options
            )

        return {
            'files_synced': files_synced,
            'size_synced': size_synced,
            'logs': self.get_logs()
        }

    def _backup_cli(self):
        """Backup VMs/Containers via vzdump CLI (runs on Proxmox host directly)"""
        vmids = self._as_list(self.source_config.get('vmids'))
        options = self.source_config.get('options', {})

        self.log("Using CLI mode (vzdump)")

        if not vmids:
            # Backup all
            vmids_arg = '--all'
        else:
            vmids_arg = ','.join(str(v) for v in vmids)

        cmd = [
            'vzdump', vmids_arg,
            '--mode', options.get('mode', 'snapshot'),
            '--compress', options.get('compress', 'zstd'),
            '--dumpdir', self.dest_path,
        ]

        if options.get('maxfiles'):
            cmd.extend(['--maxfiles', str(options['maxfiles'])])

        if options.get('bwlimit'):
            cmd.extend(['--bwlimit', str(options['bwlimit'])])

        self.log(f"Running: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=options.get('timeout', 21600)  # 6 hour default
        )

        if result.stdout:
            self.log(result.stdout)
        if result.stderr:
            self.log(result.stderr)

        if result.returncode != 0:
            raise Exception(f"vzdump failed with code {result.returncode}: {result.stderr[:500]}")

        # Calculate backup size
        size = self._get_directory_size(self.dest_path)
        files = sum(1 for _, _, fs in os.walk(self.dest_path) for _ in fs)

        self.log(f"Proxmox CLI backup completed: {files} files, {size} bytes")

        return {
            'files_synced': files,
            'size_synced': size,
            'logs': self.get_logs()
        }

    def _get_auth_ticket(self, host, port, username, password, verify_ssl):
        """Get authentication ticket from Proxmox API"""
        resp = requests.post(
            f"https://{host}:{port}/api2/json/access/ticket",
            data={'username': username, 'password': password},
            verify=verify_ssl,
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()['data']
        return {
            'Cookie': f"PVEAuthCookie={data['ticket']}",
            'CSRFPreventionToken': data['CSRFPreventionToken']
        }

    def _list_all_vmids(self, base_url, node, headers, verify_ssl):
        """List all VMs and Containers on a node"""
        vmids = []

        # Get QEMUs (VMs)
        try:
            resp = requests.get(
                f"{base_url}/nodes/{node}/qemu",
                headers=headers,
                verify=verify_ssl,
                timeout=10
            )
            resp.raise_for_status()
            for vm in resp.json().get('data', []):
                vmids.append(vm['vmid'])
        except Exception as e:
            self.log(f"ERROR: Could not list VMs: {e}")

        # Get LXC containers
        try:
            resp = requests.get(
                f"{base_url}/nodes/{node}/lxc",
                headers=headers,
                verify=verify_ssl,
                timeout=10
            )
            resp.raise_for_status()
            for ct in resp.json().get('data', []):
                vmids.append(ct['vmid'])
        except Exception as e:
            self.log(f"ERROR: Could not list containers: {e}")

        return sorted(vmids)

    def _wait_for_task(self, base_url, node, task_id, headers, verify_ssl, timeout=3600):
        """Wait for a Proxmox task to complete"""
        start = time.time()
        while time.time() - start < timeout:
            resp = requests.get(
                f"{base_url}/nodes/{node}/tasks/{task_id}/status",
                headers=headers,
                verify=verify_ssl,
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json().get('data', {})
            status = data.get('status', '')

            if status == 'stopped':
                exit_status = data.get('exitstatus', '')
                if exit_status == 'OK':
                    return
                else:
                    raise Exception(f"Task failed with exit status: {exit_status}")

            time.sleep(10)  # Poll every 10 seconds

        raise Exception(f"Task {task_id} timed out after {timeout}s")

    def _backup_vm_config(self, base_url, node, vmid, headers, verify_ssl):
        """Backup VM/Container configuration to JSON file"""
        config_path = os.path.join(self.dest_path, f"vmid-{vmid}-config.json")

        # Try QEMU first, then LXC
        for vm_type in ['qemu', 'lxc']:
            try:
                resp = requests.get(
                    f"{base_url}/nodes/{node}/{vm_type}/{vmid}/config",
                    headers=headers,
                    verify=verify_ssl,
                    timeout=10
                )
                if resp.status_code == 200:
                    config = resp.json().get('data', {})
                    config['_vmid'] = vmid
                    config['_type'] = vm_type
                    config['_backup_date'] = time.strftime("%Y-%m-%d %H:%M:%S")

                    with open(config_path, 'w') as f:
                        json.dump(config, f, indent=2)

                    self.log(f"Config saved for VMID {vmid} ({vm_type})")
                    return
            except Exception:
                continue

        self.log(f"ERROR: Could not fetch config for VMID {vmid}")

    def _download_backups(self, base_url, node, vmids, headers, verify_ssl, options):
        """Download backup files from Proxmox storage to local destination"""
        storage = options.get('storage', 'local')
        total_size = 0

        try:
            resp = requests.get(
                f"{base_url}/nodes/{node}/storage/{storage}/content",
                headers=headers,
                params={'content': 'backup'},
                verify=verify_ssl,
                timeout=30
            )
            resp.raise_for_status()

            for item in resp.json().get('data', []):
                volid = item.get('volid', '')
                item_vmid = str(item.get('vmid', ''))

                # Only download backups for our VMIDs
                if item_vmid not in [str(v) for v in vmids]:
                    continue

                # Get the most recent backup per VMID
                filename = volid.split('/')[-1] if '/' in volid else volid
                local_path = os.path.join(self.dest_path, filename)

                if os.path.exists(local_path):
                    continue  # Already downloaded

                self.log(f"Downloading {filename}...")
                try:
                    resp = requests.get(
                        f"{base_url}/nodes/{node}/storage/{storage}/file-restore/download",
                        headers=headers,
                        params={'volume': volid},
                        verify=verify_ssl,
                        stream=True,
                        timeout=3600
                    )
                    resp.raise_for_status()

                    with open(local_path, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)

                    file_size = os.path.getsize(local_path)
                    total_size += file_size
                    self.log(f"Downloaded {filename} ({file_size} bytes)")
                except Exception as e:
                    self.log(f"ERROR: Failed to download {filename}: {e}")

        except Exception as e:
            self.log(f"ERROR: Could not list backups from storage: {e}")

        return total_size
