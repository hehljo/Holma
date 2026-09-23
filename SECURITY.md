# Security Policy

## Supported Versions

Only the latest minor release receives security updates.

| Version | Supported          |
| ------- | ------------------ |
| 1.7.x   | :white_check_mark: |
| < 1.7   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability in BackupGenie, please report it privately so it can be fixed before public disclosure.

**Do not open a public GitHub issue for security bugs.**

Report via:

- GitHub Security Advisories: <https://github.com/hehljo/BackupGenie/security/advisories/new>
- Email: hehljo@gmail.com

Please include:

- A clear description of the vulnerability
- Steps to reproduce (proof-of-concept if possible)
- Affected version(s)
- Suggested fix or mitigation if you have one

## Response Timeline

- **Initial response**: within 7 days
- **Triage and severity assessment**: within 14 days
- **Fix release**: depends on severity (critical issues prioritized)

You will be credited in the release notes unless you request to remain anonymous.

## Scope

In scope:

- Authentication & authorization bypass
- Credential leakage (env vars, logs, API responses)
- SQL injection, command injection, path traversal
- Encryption issues (Fernet/PBKDF2 implementation)
- Container escape via mounted volumes
- Vulnerabilities in the backup/restore execution paths

Out of scope:

- Issues requiring physical access to the host
- Vulnerabilities in third-party dependencies (please report upstream)
- Self-XSS or social engineering attacks

## Security Best Practices

When deploying BackupGenie:

1. **Always set a strong `SECRET_KEY`** (generate it with the documented command and keep it unchanged)
2. **Change the default admin password** immediately after first login
3. **Restrict network access** to the API/UI to trusted networks (firewall rules)
4. **Use HTTPS** in production (reverse proxy with valid TLS cert)
5. **Keep credentials in the encrypted store** (Settings → Credentials), not in env vars or sources.json
6. **Regularly update** to the latest release
7. **Review backup target permissions** (filesystem ACLs, S3 bucket policies, etc.)
8. **Expose the Docker socket only when Docker backups are required**; a read-only bind mount does not make the Docker API read-only
