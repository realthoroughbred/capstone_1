"""Read repository/CI metadata using the existing Git credential helper, without logging tokens."""
import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, *args, **kwargs):
        redirected = super().redirect_request(request, *args, **kwargs)
        if redirected and urllib.parse.urlsplit(request.full_url).netloc != urllib.parse.urlsplit(redirected.full_url).netloc:
            redirected.remove_header('Authorization')
        return redirected


def api(repo, path, method='GET', body=None, raw=False):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
    result = subprocess.run(['git', '-c', 'credential.interactive=never', 'credential', 'fill'],
                            input=f'protocol=https\nhost=github.com\npath={repo}.git\n\n',
                            text=True, capture_output=True, env=env)
    if result.returncode:
        raise RuntimeError('Git credential helper has no usable session; authenticate GitHub locally')
    credentials = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    token = credentials.get('password')
    if not token:
        raise RuntimeError('Credential helper did not provide authentication')
    request = urllib.request.Request('https://api.github.com/repos/' + repo + path,
                                     headers={'Authorization': 'Bearer ' + token,
                                              'Accept': 'application/vnd.github+json',
                                              'X-GitHub-Api-Version': '2022-11-28',
                                              'User-Agent': 'team4-devsecops-verifier'},
                                     method=method,
                                     data=None if body is None else json.dumps(body).encode())
    try:
        with urllib.request.build_opener(SafeRedirect()).open(request, timeout=30) as response:
            data = response.read()
            if raw:
                return data
            return json.loads(data) if data else None
    except urllib.error.HTTPError as error:
        # Expose validation details, never headers, submitted values, or tokens.
        def safe_message(value):
            text = str(value).replace(token, '[REDACTED]')
            text = re.sub(r'(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)', '[REDACTED]', text)
            return text[:1000]
        details = {}
        try:
            response = json.loads(error.read(65536))
            if isinstance(response, dict):
                details['message'] = safe_message(response.get('message', ''))
                errors = response.get('errors', [])
                if isinstance(errors, list):
                    details['errors'] = [
                        {key: safe_message(item[key]) for key in ('resource', 'field', 'code', 'message') if key in item}
                        if isinstance(item, dict) else safe_message(item)
                        for item in errors[:10]
                    ]
        except (ValueError, OSError):
            pass
        raise RuntimeError(f'GitHub API returned HTTP {error.code} for {path or "repository"}: '
                           + json.dumps(details, ensure_ascii=False)) from None


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='realthoroughbred/capstone_1')
    parser.add_argument('--sha')
    parser.add_argument('--save', action='store_true', help='Save run metadata under evidence/github')
    args = parser.parse_args()
    try:
        repo = api(args.repo, '')
        print(json.dumps({k: repo.get(k) for k in ('full_name', 'id', 'default_branch', 'private', 'permissions')}, indent=2))
        if args.sha:
            runs = api(args.repo, '/actions/runs?head_sha=' + args.sha)
            summary = [{'id': r['id'], 'name': r['name'], 'head_sha': r['head_sha'],
                        'status': r['status'], 'conclusion': r['conclusion'], 'url': r['html_url']}
                       for r in runs['workflow_runs']]
            if args.save:
                target = Path('evidence/github')
                target.mkdir(parents=True, exist_ok=True)
                (target / 'runs.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
                (target / f'runs-{args.sha}.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
            print(json.dumps(summary, indent=2))
        else:
            print(json.dumps(api(args.repo, '/actions/oidc/customization/sub'), indent=2))
    except RuntimeError as error:
        parser.exit(1, str(error) + '\n')
