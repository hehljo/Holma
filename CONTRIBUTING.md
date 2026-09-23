# Contributing to BackupGenie

Thanks for considering a contribution! This document outlines the process for filing issues and submitting pull requests.

## Filing Issues

**Bug reports:** use the bug report template. Include:

- BackupGenie version
- Deployment platform (Synology / Pi / Linux / Docker)
- Steps to reproduce
- Expected vs actual behavior
- Relevant logs (`docker compose logs backend`)

**Feature requests:** use the feature request template. Describe the use case and what you have already tried.

## Development Setup

```bash
# Backend container, from the project root
export SECRET_KEY="development-secret-at-least-32-characters"
docker compose up -d --build backend

# Frontend
cd frontend
npm ci
npm run dev
```

The frontend dev server proxies API calls to the backend at `http://localhost:5000`.

## Adding a New Backup Source

1. Create a handler in `backend/app/backup/sources/<name>.py`
2. Extend `BackupHandler` from `backend/app/backup/base.py`
3. Implement `backup()` returning `{'files_synced': int, 'size_synced': int, 'logs': str}`
4. Register the handler type in `BackupExecutor.handlers` in `backend/app/backup/executor.py`
5. Add the source type to `frontend/src/components/SourceModal.jsx` (`SOURCE_TYPES` array + config form)
6. Add German + English labels to `frontend/src/locales/`
7. Add a regression test under `backend/tests/` and run the documented unittest, lint and build gates

## Pull Requests

1. Fork the repo and create a feature branch from `main`
2. Make focused changes (one feature / fix per PR)
3. Test locally — start the stack and verify the affected feature works end-to-end
4. Update the README if user-facing behavior changes
5. Use clear commit messages describing **what** changed (not "fix bug")
6. Open the PR against `main`

## Code Style

- **Python**: PEP 8, 4-space indent, type hints where useful
- **JavaScript/JSX**: Prettier defaults, 2-space indent, no trailing whitespace
- Keep functions small; avoid deep nesting
- Don't add comments that just restate the code

## i18n

When adding UI strings, add them to **both** language files:

- `frontend/src/locales/de/translation.json`
- `frontend/src/locales/en/translation.json`

Use `t('key.path')` from `react-i18next` in components.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
