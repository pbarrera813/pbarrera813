from pathlib import Path
import shutil
import subprocess
import textwrap
import uuid
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / '.github/workflows/profile-stats.yml').read_text(encoding='utf-8')
COMMIT_SCRIPT = textwrap.dedent(WORKFLOW.split('        run: |\n', 1)[1])
BASH = shutil.which('bash') or r'C:\Program Files\Git\bin\bash.exe'


def run(*args, cwd, check=True):
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError(f'{args[0]} failed: {result.stderr}')
    return result


def check_profile():
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    for card in (ROOT / 'profile').glob('*.svg'):
        assert f'./profile/{card.name}' in readme, card.name
        document = ET.parse(card).getroot()
        assert document.tag == '{http://www.w3.org/2000/svg}svg', card.name
        assert 'Something went wrong' not in ' '.join(document.itertext()), card.name

    base = ROOT / f'.profile-stats-check-{uuid.uuid4().hex}'
    # Inherit workspace permissions so Git can access fixtures in a Windows sandbox.
    base.mkdir()
    try:
        remote, checkout = base / 'remote.git', base / 'checkout'
        run('git', 'init', '--bare', '--initial-branch=main', str(remote), cwd=base)
        run('git', 'init', '--initial-branch=main', str(checkout), cwd=base)
        run('git', 'config', 'user.name', 'Profile workflow test', cwd=checkout)
        run('git', 'config', 'user.email', 'test@example.invalid', cwd=checkout)
        shutil.copytree(ROOT / 'profile', checkout / 'profile')
        (checkout / 'README.md').write_text('Original README\n', encoding='utf-8')
        run('git', 'add', '.', cwd=checkout)
        run('git', 'commit', '-m', 'Test fixture', cwd=checkout)
        run('git', 'remote', 'add', 'origin', str(remote), cwd=checkout)
        run('git', 'push', '-u', 'origin', 'main', cwd=checkout)

        def remote_head():
            return run('git', 'rev-parse', 'main', cwd=remote).stdout.strip()

        def commit_cards(check=True):
            return run(BASH, '--noprofile', '--norc', '-e', '-o', 'pipefail',
                       '-c', COMMIT_SCRIPT, cwd=checkout, check=check)

        changed_card = checkout / 'profile/stats-light.svg'
        changed_card.write_bytes(changed_card.read_bytes() + b'\n')
        (checkout / 'README.md').write_text('Unrelated pending edit\n', encoding='utf-8')
        previous = remote_head()
        commit_cards()
        assert remote_head() != previous, 'Changed cards were not pushed'
        files = run('git', 'diff-tree', '--no-commit-id', '--name-only', '-r',
                    'HEAD', cwd=checkout).stdout.splitlines()
        assert files == ['profile/stats-light.svg'], files
        assert run('git', 'diff', '--name-only', cwd=checkout).stdout.strip() == 'README.md'

        previous = remote_head()
        commit_cards()
        assert remote_head() == previous, 'Unchanged cards created a commit'

        changed_card.write_bytes(changed_card.read_bytes() + b'\n')
        (checkout / '.git/hooks/pre-commit').write_text('#!/bin/sh\nexit 1\n', encoding='utf-8')
        (checkout / '.git/hooks/pre-commit').chmod(0o755)
        assert commit_cards(check=False).returncode != 0, 'Commit failure was suppressed'
        assert remote_head() == previous, 'Failed commit was pushed'

        (checkout / 'profile/stats-dark.svg').unlink()
        assert commit_cards(check=False).returncode != 0, 'Missing card failure was suppressed'
        assert remote_head() == previous, 'Incomplete cards were pushed'
    finally:
        assert base.resolve().parent == ROOT
        for file in base.rglob('*'):
            if file.is_file():
                file.chmod(0o666)
        shutil.rmtree(base)

    print('Passed: SVG validation, scoped update, unchanged update, commit failure, missing card.')


if __name__ == '__main__':
    check_profile()
