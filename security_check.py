"""Scan publication files or exact staged blobs without printing matched secrets."""
from pathlib import Path
import argparse
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parent
TOKEN_PATTERNS = [
    re.compile(rb'\bsk-[A-Za-z0-9][A-Za-z0-9_-]{19,}'),
    re.compile(rb'\bgh[pousr]_[A-Za-z0-9]{20,}'),
    re.compile(rb'\bgithub_pat_[A-Za-z0-9_]{20,}'),
    re.compile(rb'\bAIza[A-Za-z0-9_-]{30,}'),
    re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
]
SECRET_FIELDS = re.compile(r'(?:api[_-]?key|auth[_-]?token|access[_-]?token|secret[_-]?access[_-]?key|private[_-]?key|password)$', re.I)


def real_value(value):
    return (isinstance(value, str) and len(value.strip()) >= 12
            and not any(marker in value.lower() for marker in ['${', 'your_', 'example', 'placeholder', 'redacted', 'dummy', 'test-']))


def suspicious_field(value):
    if isinstance(value, dict):
        return any((SECRET_FIELDS.search(k) and real_value(v)) or suspicious_field(v) for k, v in value.items())
    if isinstance(value, list):
        return any(suspicious_field(v) for v in value)
    return False


def forbidden(path):
    p = Path(path)
    parts = p.parts
    if any(x in {'.git', '.idea', '__pycache__', 'node_modules', 'sessions'} or x.startswith('.venv') for x in parts):
        return True
    if p.name in {'.harbor-agents.env.example', '.env.example'}:
        return False
    return '.env' in p.name or p.suffix.lower() in {'.pem', '.key', '.p12', '.pfx', '.db'}


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true')
    parser.add_argument('--secret-file', type=Path, action='append', default=[])
    args = parser.parse_args()
    known = []
    for path in args.secret_file:
        for line in path.read_text(encoding='utf-8').splitlines():
            if '=' not in line or line.lstrip().startswith('#'):
                continue
            name, value = line.split('=', 1)
            value = value.strip().strip(chr(34)).strip(chr(39))
            if any(term in name.upper() for term in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD')) and len(value) >= 12 and not value.startswith('${'):
                known.append(value.encode())
    if args.staged:
        paths = [x.decode('utf-8') for x in git('ls-files', '-z').split(b'\0') if x]
        entries = ((path, git('show', ':' + path)) for path in paths)
    else:
        paths = [p for p in ROOT.rglob('*') if p.is_file() and '.git' not in p.relative_to(ROOT).parts
                 and not any(x in {'SkillEvolBench', '__pycache__'} for x in p.relative_to(ROOT).parts)]
        entries = ((str(p.relative_to(ROOT)).replace('\\', '/'), p.read_bytes()) for p in paths)
    failures = []
    for path, data in entries:
        labels = []
        if forbidden(path):
            labels.append('forbidden file')
        if any(secret in data for secret in known):
            labels.append('known local credential')
        if any(pattern.search(data) for pattern in TOKEN_PATTERNS):
            labels.append('credential-shaped content')
        if path.endswith('.json'):
            try:
                if suspicious_field(json.loads(data)):
                    labels.append('populated credential field')
            except (ValueError, UnicodeDecodeError):
                labels.append('invalid JSON')
        if labels:
            failures.append({'path': path, 'findings': labels})
    print(json.dumps({'mode': 'staged blobs' if args.staged else 'publication files',
                      'files_checked': len(paths), 'finding_count': len(failures), 'findings': failures}, ensure_ascii=False))
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
