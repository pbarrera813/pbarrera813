import json
import os
import urllib.request
from pathlib import Path

USER = 'pbarrera813'
# The workflow token cannot see which repositories the user may push to, so list them here.
WRITE_ACCESS = ['TheodoreMeyer/SimpleVoice-Geyser', 'TheodoreMeyer/Svg-App']
PROFILE = Path(__file__).resolve().parents[1] / 'profile'
THEMES = {
    'light': dict(title='#0969da', text='#59636e', bg='#ffffff', border='#d1d9e0'),
    'dark': dict(title='#4493f8', text='#9198a1', bg='#0d1117', border='#3d444d'),
}


def fetch(path):
    headers = {'Accept': 'application/vnd.github+json'}
    if os.environ.get('GITHUB_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['GITHUB_TOKEN']
    request = urllib.request.Request('https://api.github.com/' + path, headers=headers)
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read() or '[]')


def totals(get=fetch):
    owned = get(f'users/{USER}/repos?type=owner&per_page=100')
    names = [repo['full_name'] for repo in owned if not repo['fork']] + WRITE_ACCESS
    stars = commits = 0
    for name in names:
        stars += get(f'repos/{name}')['stargazers_count']
        contributors = get(f'repos/{name}/contributors?per_page=100')
        commits += sum(c['contributions'] for c in contributors if c['login'] == USER)
    return stars, commits


def render(stars, commits, theme):
    c = THEMES[theme]
    rows = ''.join(
        f'<text x="25" y="{y}" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="14" '
        f'font-weight="700" fill="{c["text"]}">{label}</text>'
        f'<text x="215" y="{y}" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="14" '
        f'font-weight="700" fill="{c["text"]}">{value:,}</text>'
        for y, label, value in ((75, 'Stars earned:', stars), (104, 'Commits:', commits))
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="360" height="132" viewBox="0 0 360 132" '
        'role="img" aria-labelledby="title desc">'
        '<title id="title">GitHub activity</title>'
        f'<desc id="desc">Stars earned: {stars}, commits: {commits}, across public repositories I own or can push to</desc>'
        f'<rect x="0.5" y="0.5" width="359" height="131" rx="4.5" fill="{c["bg"]}" stroke="{c["border"]}"/>'
        f'<text x="25" y="35" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="18" '
        f'font-weight="600" fill="{c["title"]}">GitHub activity</text>'
        + rows + '</svg>\n'
    )


if __name__ == '__main__':
    stars, commits = totals()
    for theme in THEMES:
        (PROFILE / f'stats-{theme}.svg').write_text(render(stars, commits, theme), encoding='utf-8')
    print(f'stars={stars} commits={commits}')
