"""Regression coverage for the VPC read permission required after creation."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BootstrapScopeTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'generated').mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(prefix='bootstrap-test-', dir=ROOT / 'generated')
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.plan = self.path / 'plan.json'
        self.plan.write_text(json.dumps({'variables': {k: {'value': v} for k, v in {
            'aws_account_id': '852093844554', 'region': 'ap-northeast-2',
            'project': 'team4', 'cluster_name': 'team4-eks',
            'enable_inspector_response': False, 'node_instance_type': 't3.large'}.items()}, 'resource_changes': []}))

    def render(self, phase, vpc='vpc-11111111111111111', template='lt-66666666666666666'):
        arguments = [sys.executable, str(ROOT / 'docs/admin-bootstrap/render.py'),
                     '--plan', str(self.plan), '--phase', phase, '--out', str(self.path / 'output'),
                     '--vpc-id', vpc, '--default-sg-id', 'sg-22222222222222222']
        if phase in ('cluster', 'nodes'):
            arguments += ['--subnet-a-id', 'subnet-33333333333333333',
                          '--subnet-c-id', 'subnet-44444444444444444', '--node-sg-id', 'sg-55555555555555555',
                          '--issuer-url', 'https://oidc.eks.ap-northeast-2.amazonaws.com/id/' + 'A' * 32]
        if phase == 'nodes':
            arguments += ['--launch-template-id', template]
        return subprocess.run(arguments, capture_output=True, text=True, timeout=15)

    def assert_attribute_scope(self, phase):
        result = self.render(phase)
        self.assertEqual(result.returncode, 0, result.stderr)
        policy = json.loads((self.path / 'output/operator-new-resource-bootstrap.json').read_text())
        statements = policy['Statement']
        read = [s for s in statements if s['Action'] == 'ec2:DescribeVpcAttribute']
        self.assertEqual(len(read), 1)
        self.assertEqual(read[0]['Effect'], 'Allow')
        self.assertEqual(read[0]['Resource'], 'arn:aws:ec2:ap-northeast-2:852093844554:vpc/vpc-11111111111111111')
        self.assertTrue(all('*' not in s['Resource'] for s in statements))
        self.assertEqual(len(statements), 2 if phase == 'network' else 3)

    def test_network_recovery_read_is_limited_to_observed_new_vpc(self):
        self.assert_attribute_scope('network')

    def test_cluster_update_preserves_exact_vpc_read_permission(self):
        self.assert_attribute_scope('cluster')

    def test_existing_default_vpc_is_rejected(self):
        result = self.render('network', vpc='vpc-044ea157cc2bf6edc')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.path / 'output/operator-new-resource-bootstrap.json').exists())

    def test_node_launch_permissions_require_exact_template_and_project_instance_type(self):
        result = self.render('nodes')
        self.assertEqual(result.returncode, 0, result.stderr)
        document = json.loads((self.path / 'output/operator-new-resource-bootstrap.json').read_text())
        statements = {s['Sid']: s for s in document['Statement']}
        launch = [s for s in statements.values() if s['Action'] == 'ec2:RunInstances']
        self.assertEqual(len(launch), 2)
        for statement in launch:
            self.assertEqual(statement['Condition']['ArnEquals']['ec2:LaunchTemplate'],
                             'arn:aws:ec2:ap-northeast-2:852093844554:launch-template/lt-66666666666666666')
        resources = statements['OnlyObservedNodeLaunchResources']['Resource']
        self.assertEqual([r.rsplit('/', 1)[1] for r in resources if ':subnet/' in r],
                         ['subnet-33333333333333333', 'subnet-44444444444444444'])
        self.assertEqual([r.rsplit('/', 1)[1] for r in resources if ':security-group/' in r], ['sg-55555555555555555'])
        self.assertNotIn('arn:aws:ec2:ap-northeast-2:852093844554:instance/*', resources)
        condition = statements['OnlyTaggedT3LargeNodes']['Condition']['StringEquals']
        self.assertEqual(condition, {'ec2:InstanceType': 't3.large', 'aws:RequestTag/Project': 'team4',
                                    'aws:RequestTag/ManagedBy': 'Terraform'})
        self.assertEqual(statements['TagNewNodeInstancesOnly']['Condition']['StringEquals']['ec2:CreateAction'], 'RunInstances')
        bucket = statements['ReadOwnEvidenceBucketConfiguration']
        self.assertEqual(bucket['Resource'], 'arn:aws:s3:::team4-852093844554-ap-northeast-2-evidence')
        self.assertTrue(all(action.startswith('s3:Get') for action in bucket['Action']))

    def test_node_bootstrap_rejects_wildcard_template(self):
        self.assertNotEqual(self.render('nodes', template='lt-*').returncode, 0)

    def test_node_bootstrap_rejects_unapproved_larger_instance_type(self):
        plan = json.loads(self.plan.read_text())
        plan['variables']['node_instance_type']['value'] = 'm5.24xlarge'
        self.plan.write_text(json.dumps(plan))
        self.assertNotEqual(self.render('nodes').returncode, 0)


if __name__ == '__main__':
    unittest.main()
