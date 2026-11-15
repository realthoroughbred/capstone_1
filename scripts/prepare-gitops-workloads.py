"""Render a separate GitOps workload using an explicitly approved immutable ECR image.

Does not push Git, contact AWS or apply to Kubernetes. Review and commit output,
then point Argo at that commit. Inspector continues to own only demo/server.
"""
import argparse
import json
import re
from pathlib import Path


def render(image, commit):
    if not re.fullmatch(r'[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/[a-z0-9_./-]+@sha256:[a-f0-9]{64}', image):
        raise ValueError('An explicitly approved ECR manifest digest is required')
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Full build source commit required')
    container = {'name': 'test', 'image': image, 'ports': [{'containerPort': 8080}],
                 'securityContext': {'allowPrivilegeEscalation': False, 'readOnlyRootFilesystem': True, 'capabilities': {'drop': ['ALL']}},
                 'resources': {'requests': {'cpu': '10m', 'memory': '16Mi'}, 'limits': {'cpu': '100m', 'memory': '64Mi'}},
                 'readinessProbe': {'httpGet': {'path': '/', 'port': 8080}, 'initialDelaySeconds': 2}}
    deployment = {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'metadata': {'name': 'gitops-server', 'namespace': 'demo'},
                  'spec': {'replicas': 1, 'selector': {'matchLabels': {'app': 'gitops-server'}}, 'template': {
                    'metadata': {'labels': {'app': 'gitops-server', 'project': 'team4'}, 'annotations': {'team4/source-commit': commit}},
                    'spec': {'automountServiceAccountToken': False, 'securityContext': {'runAsNonRoot': True, 'runAsUser': 10001,
                             'seccompProfile': {'type': 'RuntimeDefault'}}, 'containers': [container]}}}}
    service = {'apiVersion': 'v1', 'kind': 'Service', 'metadata': {'name': 'gitops-server', 'namespace': 'demo'},
               'spec': {'selector': {'app': 'gitops-server'}, 'ports': [{'port': 8080, 'targetPort': 8080}]}}
    network = {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy', 'metadata': {'name': 'gitops-server-client-only', 'namespace': 'demo'},
               'spec': {'podSelector': {'matchLabels': {'app': 'gitops-server'}}, 'policyTypes': ['Ingress'],
                        'ingress': [{'from': [{'podSelector': {'matchLabels': {'app': 'client'}}}], 'ports': [{'protocol': 'TCP', 'port': 8080}]}]}}
    egress = {'apiVersion': 'networking.k8s.io/v1', 'kind': 'NetworkPolicy', 'metadata': {'name': 'gitops-client-egress', 'namespace': 'demo'},
              'spec': {'podSelector': {'matchLabels': {'app': 'client'}}, 'policyTypes': ['Egress'],
                       'egress': [{'to': [{'podSelector': {'matchLabels': {'app': 'gitops-server'}}}], 'ports': [{'protocol': 'TCP', 'port': 8080}]}]}}
    return {'apiVersion': 'v1', 'kind': 'List', 'items': [deployment, service, network, egress]}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', required=True)
    p.add_argument('--build-commit', required=True)
    p.add_argument('--output-dir', type=Path, default=Path('k8s/gitops/approved-workloads'))
    a=p.parse_args()
    document=render(a.image,a.build_commit)
    a.output_dir.mkdir(parents=True,exist_ok=False)
    (a.output_dir/'workloads.json').write_text(json.dumps(document,indent=2)+'\n')
    print('Rendered for review; commit this directory before enabling the Argo application.')
