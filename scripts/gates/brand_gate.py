#!/usr/bin/env python3
"""
Gate: the product name has exactly one source per runtime.

Checks
  1. No display form of the old product name anywhere in tracked text files.
     A lower-case occurrence glued into a path or identifier
     (`/data/<old>.db`, `RCLONE_CONFIG_<OLD>_TEMP`) is a technical contract
     with stored data and allowed; a capitalised or free-standing one is text
     someone reads.
  2. The current name is not typed into a display path: frontend sources,
     translations, index.html and backend code must take it from
     frontend/src/brand.js or backend/app/brand.py.
  3. No hand-maintained web manifest (it is generated from brand.js).
  4. The frontend version and the backend version are the same, and no
     version number is typed into a component.

Exit: 0 = passed, 1 = failed, 2 = not measured (inputs missing, nothing scanned)
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Split so this file does not carry the name it looks for.
LEGACY = 'Backup' + 'Genie'

failures = []
checked = {'files': 0, 'display_files': 0}


def fail(msg):
    failures.append(msg)


def read(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as fh:
        return fh.read()


def tracked_text_files():
    out = subprocess.run(['git', 'ls-files', '-co', '--exclude-standard'], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout.split('\n')
    for rel in out:
        if not rel or rel.startswith(('frontend/dist/', 'frontend/node_modules/')):
            continue
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding='utf-8') as fh:
                yield rel, fh.read()
        except (UnicodeDecodeError, OSError):
            continue  # binary


def strip_comments(rel, text):
    if rel.endswith(('.js', '.jsx')):
        text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
        return re.sub(r'(^|\s)//[^\n]*', r'\1', text)
    if rel.endswith('.py'):
        text = re.sub(r'"""(.*?)"""', '', text, flags=re.S)
        return re.sub(r'#[^\n]*', '', text)
    return text


def main():
    brand_js = 'frontend/src/brand.js'
    brand_py = 'backend/app/brand.py'
    try:
        js_src, py_src = read(brand_js), read(brand_py)
    except OSError as e:
        print(f'NICHT GEMESSEN: Markenquelle fehlt ({e})')
        return 2
    m_js = re.search(r"\bname:\s*'([^']+)'", js_src)
    m_py = re.search(r"^BRAND_NAME\s*=\s*'([^']+)'", py_src, re.M)
    if not m_js or not m_py:
        print('NICHT GEMESSEN: Markenname in brand.js/brand.py nicht gefunden')
        return 2
    brand = m_js.group(1)
    if m_py.group(1) != brand:
        fail(f'brand.py sagt {m_py.group(1)!r}, brand.js sagt {brand!r}')

    # 1 + 2 -----------------------------------------------------------------
    legacy_display = re.compile(rf'(?<![/._-]){LEGACY}|(?<![A-Za-z0-9/._-]){LEGACY.lower()}(?![A-Za-z0-9/._-])')
    brand_literal = re.compile(rf'\b{re.escape(brand)}\b')
    self_rel = os.path.relpath(os.path.abspath(__file__), ROOT)
    for rel, text in tracked_text_files():
        if rel == self_rel:
            continue
        checked['files'] += 1
        for n, line in enumerate(text.split('\n'), 1):
            if legacy_display.search(line):
                fail(f'{rel}:{n}: alter Produktname im Text: {line.strip()[:90]}')

        display = (
            (rel.startswith('frontend/src/') and rel != brand_js)
            or rel == 'frontend/index.html'
            or (rel.startswith('backend/app/') and rel.endswith('.py') and rel != brand_py)
        )
        if display:
            checked['display_files'] += 1
            for n, line in enumerate(strip_comments(rel, text).split('\n'), 1):
                if brand_literal.search(line):
                    fail(f'{rel}:{n}: Markenname fest im Anzeigepfad: {line.strip()[:90]}')

    # 3 ---------------------------------------------------------------------
    if os.path.exists(os.path.join(ROOT, 'frontend/public/manifest.webmanifest')):
        fail('frontend/public/manifest.webmanifest ist handgepflegt - wird aus brand.js erzeugt')

    # 4 ---------------------------------------------------------------------
    import json
    fe_version = json.loads(read('frontend/package.json')).get('version')
    m_ver = re.search(r"^APP_VERSION\s*=\s*'([^']+)'", read('backend/app/version.py'), re.M)
    if not fe_version or not m_ver:
        print('NICHT GEMESSEN: Versionsquelle fehlt')
        return 2
    if fe_version != m_ver.group(1):
        fail(f'Version driftet: frontend {fe_version} / backend {m_ver.group(1)}')
    for rel, text in tracked_text_files():
        if rel.startswith('frontend/src/') and rel.endswith('.jsx'):
            for n, line in enumerate(text.split('\n'), 1):
                if re.search(r'>\s*v\d+\.\d+\.\d+\s*<', line):
                    fail(f'{rel}:{n}: Versionsnummer fest im Markup')

    if checked['files'] == 0 or checked['display_files'] == 0:
        print(f'NICHT GEMESSEN: {checked}')
        return 2
    if failures:
        print(f'ROT: {len(failures)} Befunde ({checked["files"]} Dateien, '
              f'{checked["display_files"]} im Anzeigepfad geprüft)')
        for f in failures[:40]:
            print(f'  - {f}')
        return 1
    print(f'GRUEN: Marke "{brand}" v{fe_version} - {checked["files"]} Dateien, '
          f'{checked["display_files"]} im Anzeigepfad geprüft')
    return 0


if __name__ == '__main__':
    sys.exit(main())
