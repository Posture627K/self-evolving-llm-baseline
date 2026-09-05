"""Clone the pinned upstream and safely apply the recorded four-file patch."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parent


def git(repo, *args, capture=False):
    return subprocess.run(['git', '-C', str(repo), *args], check=True,
                          stdout=subprocess.PIPE if capture else None, text=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo-dir', type=Path, default=ROOT / 'SkillEvolBench')
    p.add_argument('--existing-only', action='store_true', help='Do not clone or fetch; only check/apply to the pinned existing checkout.')
    args = p.parse_args()
    repo = args.repo_dir.expanduser().resolve()
    manifest = json.loads((ROOT / 'upstream/manifest.json').read_text(encoding='utf-8'))
    patch = ROOT / 'upstream' / manifest['patch']
    if hashlib.sha256(patch.read_bytes()).hexdigest() != manifest['patch_sha256']:
        raise SystemExit('Patch checksum mismatch.')
    if not (repo / '.git').is_dir():
        if args.existing_only or repo.exists():
            raise SystemExit('Expected a Git checkout; refusing to overwrite an existing directory.')
        repo.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'clone', '--no-checkout', manifest['repository'], str(repo)], check=True)
        git(repo, 'checkout', '--detach', manifest['commit'])
    head = git(repo, 'rev-parse', 'HEAD', capture=True).stdout.strip()
    if head != manifest['commit']:
        raise SystemExit('Unexpected upstream HEAD; refusing to reset or switch this checkout.')
    def patch_matches():
        return all(hashlib.sha256((repo / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() == digest
                   for name, digest in manifest['modified_files'].items())
    if not patch_matches():
        if git(repo, 'diff', '--name-only', capture=True).stdout.strip() or git(repo, 'diff', '--cached', '--name-only', capture=True).stdout.strip():
            raise SystemExit('Upstream has unrecognized tracked edits; refusing to overwrite them.')
        git(repo, 'apply', '--check', str(patch))
        git(repo, 'apply', str(patch))
    if not patch_matches():
        raise SystemExit('Patched file checksum mismatch.')
    print('Pinned upstream and four-file patch: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
