#!/usr/bin/env python3
"""Check tracked files for private paths, obvious credentials and PNG metadata.

This is a regression guard, not a claim of exhaustive secret detection.
"""
from pathlib import Path
import re
import subprocess
from sanitize_png import sanitize

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    'private-home-path': re.compile(r'(?:/Users/|/home/)[A-Za-z0-9_.-]+/|[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s]+'),
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'github-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{60,})\b'),
    'aws-key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'api-token': re.compile(r'\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{30,}|xox[baprs]-[A-Za-z0-9-]{20,}|AIza[A-Za-z0-9_-]{35})\b'),
    'personal-email': re.compile(r'\b[A-Za-z0-9._%+-]+@(?:gmail|hotmail|outlook|yahoo|icloud)\.[A-Za-z]{2,}\b'),
}


def main():
    paths = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    problems = []
    texts = pngs = 0
    for name in filter(None, paths):
        file = ROOT / name
        if file.is_symlink():
            problems.append((name, 'symlink'))
            continue
        raw = file.read_bytes()
        if file.suffix.lower() == '.png':
            pngs += 1
            try:
                _, removed = sanitize(raw)
                if removed:
                    problems.append((name, 'PNG metadata: ' + ', '.join(removed)))
            except ValueError:
                problems.append((name, 'invalid PNG'))
            continue
        try:
            text = raw.decode('utf8')
        except UnicodeDecodeError:
            problems.append((name, 'unrecognized binary; review required'))
            continue
        texts += 1
        for label, pattern in PATTERNS.items():
            if pattern.search(text):
                problems.append((name, label))
    for name, label in problems:
        # Do not reproduce sensitive matching text in logs.
        print(f'{name}: {label}')
    print(f'Checked {texts} text files and {pngs} PNG files; {len(problems)} findings.')
    return int(bool(problems))


if __name__ == '__main__':
    raise SystemExit(main())
