"""Configure Argo GitHub App auth when repository deploy keys are disabled.

App must have contents:read and be installed on exactly this one repository.
Only the private key file is read; JWT/access token/Secret values are never logged.
GitHub must already have the reviewed App installation; this script creates no App.
"""
import argparse
import base64
import json
import subprocess
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


def validate_installation(info):
    permissions=info.get('permissions', {})
    if permissions.get('contents')!='read' or any(v!='read' for v in permissions.values()):
        raise ValueError('GitHub App permissions must be read-only, including contents:read')
    if info.get('repository_selection')!='selected' or info.get('suspended_at'):
        raise ValueError('Use an active installation restricted to selected repositories')


def api(path, token, data=None, method=None):
    req=urllib.request.Request('https://api.github.com'+path,
        data=None if data is None else json.dumps(data).encode(),
        headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
                 'X-GitHub-Api-Version':'2022-11-28','User-Agent':'capstone-gitops-setup'}, method=method)
    try:
        with urllib.request.urlopen(req,timeout=20) as response:
            raw=response.read()
            return json.loads(raw) if raw else {}
    except Exception:
        raise RuntimeError('GitHub App API request failed; credentials not logged') from None


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--app-id',required=True)
    p.add_argument('--installation-id',required=True)
    p.add_argument('--private-key-file',type=Path,required=True)
    p.add_argument('--context',choices=['kind-team4','team4-eks'],required=True)
    p.add_argument('--approved-aws-test',action='store_true')
    p.add_argument('--expected-api-server')
    p.add_argument('--inspect-only',action='store_true')
    a=p.parse_args()
    if not a.app_id.isdigit() or not a.installation_id.isdigit():
        p.error('numeric App/installation IDs required')
    kube=['kubectl','--context',a.context]
    server=subprocess.check_output(kube+['config','view','--minify','-o','jsonpath={.clusters[0].cluster.server}'],text=True).strip()
    if a.context=='kind-team4':
        if urlparse(server).hostname not in ['127.0.0.1','localhost','::1']:
            raise ValueError('Not a local endpoint')
    elif not a.approved_aws_test or not a.expected_api_server or server!=a.expected_api_server:
        raise ValueError('Approved exact AWS endpoint required')
    encode=lambda x: base64.urlsafe_b64encode(x).rstrip(b'=')
    now=int(time.time())
    payload=encode(b'{"alg":"RS256","typ":"JWT"}')+b'.'+encode(json.dumps({'iat':now-60,'exp':now+540,'iss':a.app_id}).encode())
    signature=subprocess.run(['openssl','dgst','-sha256','-sign',str(a.private_key_file)],input=payload,capture_output=True,check=True).stdout
    jwt=(payload+b'.'+encode(signature)).decode()
    info=api('/app/installations/'+a.installation_id,jwt)
    validate_installation(info)
    token=api('/app/installations/'+a.installation_id+'/access_tokens',jwt,{})['token']
    try:
        repos=api('/installation/repositories?per_page=100',token)
        if repos.get('total_count')!=1 or repos['repositories'][0]['full_name']!='realthoroughbred/capstone_1':
            raise ValueError('App installation must be dedicated to realthoroughbred/capstone_1')
    finally:
        api('/installation/token',token,method='DELETE')
    if a.inspect_only:
        print('PASS: read-only App installation is restricted to the intended repository')
        return
    existing=subprocess.check_output(kube+['-n','argocd','get','secret','team4-gitops-repository','--ignore-not-found','-o','name'],text=True)
    if existing.strip():
        raise ValueError('Existing auth preserved; review before replacing it')
    secret={'apiVersion':'v1','kind':'Secret','metadata':{'name':'team4-gitops-repository','namespace':'argocd',
            'labels':{'argocd.argoproj.io/secret-type':'repository'}},'type':'Opaque',
            'stringData':{'type':'git','url':'https://github.com/realthoroughbred/capstone_1.git',
                          'githubAppID':a.app_id,'githubAppInstallationID':a.installation_id,
                          'githubAppPrivateKey':a.private_key_file.read_text()}}
    response=subprocess.run(kube+['create','-f','-'],input=json.dumps(secret),text=True,capture_output=True)
    if response.returncode:
        raise RuntimeError('Argo repository Secret creation failed; key not logged')
    print('Configured GitHub App authentication; verify Argo connection and exact synced commit separately.')


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        raise SystemExit('Auth setup failed: '+type(exc).__name__+'; no credentials logged') from None
