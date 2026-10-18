"""Prove real Argo CD comparison/reconciliation; never repair NetworkPolicy directly."""
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

context, revision = sys.argv[1:]
if context not in ('kind-team4', 'team4-eks'):
    raise SystemExit('Unexpected context')
cmd = ['kubectl', '--context', context]
out = Path(f'evidence/gitops-{context}.json')
evidence = {'context': context, 'revision': revision, 'result': 'FAIL', 'events': []}
def run(*args, check=True):
    return subprocess.run(cmd + list(args), text=True, capture_output=True, check=check)
def read(namespace, kind, name):
    return json.loads(run('-n', namespace, 'get', kind, name, '-o', 'json').stdout)
def app():
    return read('argocd', 'application', 'team4-network')
def record(event, **details):
    evidence['events'].append({'event': event, 'time_utc': datetime.now(timezone.utc).isoformat(), **details})
    out.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(event, flush=True)
def wait_for(description, test, timeout=240):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if test(): return
        time.sleep(2)
    raise RuntimeError('Timed out: ' + description)
def patch_app(automated):
    run('-n', 'argocd', 'patch', 'application', 'team4-network', '--type', 'merge',
        '-p', json.dumps({'spec': {'syncPolicy': {'automated': automated}}}))
def refresh():
    run('-n', 'argocd', 'annotate', 'application', 'team4-network', 'argocd.argoproj.io/refresh=normal', '--overwrite')
def synced():
    status = app().get('status', {})
    return status.get('sync', {}).get('status') == 'Synced' and status.get('sync', {}).get('revision') == revision
restore = None
try:
    wait_for('initial Argo sync of published commit', synced, 600)
    original = app()
    restore = original['spec']['syncPolicy']['automated']
    if not restore.get('selfHeal') or restore.get('enabled') is False:
        raise RuntimeError('Application must enable automated selfHeal')
    baseline = read('demo', 'networkpolicy', 'allow-client-to-server')['spec']
    if not baseline.get('ingress'):
        raise RuntimeError('Baseline must contain client ingress permission')
    initial_operation = original.get('status', {}).get('operationState', {}).get('finishedAt')
    record('BASELINE_SYNCED', spec=baseline)
    # Temporarily stop reconciliation to measure actual drift and its traffic
    # effect. Admission and GitOps are separate: patch MUST be admitted here.
    patch_app({**restore, 'enabled': False})
    run('-n', 'demo', 'patch', 'networkpolicy', 'allow-client-to-server', '--type', 'merge', '-p', '{"spec":{"ingress":[]}}')
    if read('demo', 'networkpolicy', 'allow-client-to-server')['spec'].get('ingress'):
        raise RuntimeError('Drift patch was not applied')
    record('DRIFT_ADMITTED', spec=read('demo', 'networkpolicy', 'allow-client-to-server')['spec'])
    refresh()
    wait_for('Argo OutOfSync detection', lambda: app().get('status', {}).get('sync', {}).get('status') == 'OutOfSync')
    record('DRIFT_DETECTED_OUTOFSYNC')
    ip = read('demo', 'service', 'server')['spec']['clusterIP']
    run('-n', 'demo', 'exec', 'deployment/server', '--', 'wget', '-T', '3', '-qO-', 'http://127.0.0.1:8080')
    # Require convergence to blocked traffic; the endpoint is separately healthy.
    wait_for('restrictive drift blocks client', lambda: run('-n', 'demo', 'exec', 'deployment/client', '--',
             'wget', '-T', '3', '-qO-', f'http://{ip}:8080', check=False).returncode != 0)
    run('-n', 'demo', 'exec', 'deployment/client', '--', 'true')
    record('DRIFT_TRAFFIC_BLOCKED')
    start = time.monotonic()
    patch_app(restore)
    refresh()
    def restored():
        state = app().get('status', {}).get('operationState', {})
        return (synced() and read('demo', 'networkpolicy', 'allow-client-to-server')['spec'] == baseline
                and state.get('phase') == 'Succeeded' and state.get('finishedAt') != initial_operation
                and state.get('syncResult', {}).get('revision') == revision)
    wait_for('Argo automatic restoration and successful sync operation', restored, 300)
    record('AUTOMATIC_RESTORE_VERIFIED', elapsed_seconds=round(time.monotonic() - start, 3),
           operation=app()['status']['operationState'], restored_spec=read('demo', 'networkpolicy', 'allow-client-to-server')['spec'])
    wait_for('client connectivity restored', lambda: run('-n', 'demo', 'exec', 'deployment/client', '--',
             'wget', '-T', '3', '-qO-', f'http://{ip}:8080', check=False).returncode == 0)
    evidence['result'] = 'PASS'
    record('PASS: GitOps detected real admitted drift, restored it, and restored connectivity')
except (RuntimeError, subprocess.CalledProcessError) as error:
    record('FAIL', reason=str(error))
    raise SystemExit(1) from error
finally:
    if restore is not None:
        patch_app(restore)
        refresh()
