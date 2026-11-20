import importlib.util
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


def check_totals():
    spec = importlib.util.spec_from_file_location('maintained_stats', ROOT / 'scripts/maintained_stats.py')
    stats = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stats)

    repos = {
        f'users/{stats.USER}/repos?type=owner&per_page=100': [
            {'full_name': 'me/own', 'fork': False},
            {'full_name': 'me/forked', 'fork': True},
        ],
        'repos/me/own': {'stargazers_count': 2},
        'repos/me/own/contributors?per_page=100': [
            {'login': stats.USER, 'contributions': 5}, {'login': 'other', 'contributions': 9}],
    }
    for name in stats.WRITE_ACCESS:
        repos[f'repos/{name}'] = {'stargazers_count': 10}
        repos[f'repos/{name}/contributors?per_page=100'] = [
            {'login': 'other', 'contributions': 50}, {'login': stats.USER, 'contributions': 3}]
    expected = (2 + 10 * len(stats.WRITE_ACCESS), 5 + 3 * len(stats.WRITE_ACCESS))
    assert stats.totals(repos.__getitem__) == expected, 'Forks, others or write-access repos miscounted'

    for theme in stats.THEMES:
        text = ' '.join(ET.fromstring(stats.render(1234, 56, theme)).itertext())
        assert '1,234' in text and '56' in text, theme


def check_profile():
    check_totals()
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    for card in (ROOT / 'profile').glob('*.svg'):
        assert f'./profile/{card.name}' in readme, card.name
        document = ET.parse(card).getroot()
        assert document.tag == '{http://www.w3.org/2000/svg}svg', card.name
        assert 'Something went wrong' not in ' '.join(document.itertext()), card.name

    base = ROOT / f'.profile-stats-check-{uuid.uuid4().hex}'
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
