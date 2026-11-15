import importlib.util
import unittest
from pathlib import Path


def load(name):
    path=Path(__file__).resolve().parents[1]/'scripts'/name
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FinalizationToolsTests(unittest.TestCase):
    def test_rto_uses_whole_interval_and_never_claims_mock_as_aws(self):
        timing=load('recovery-timing.py')
        self.assertEqual(timing.assess({'handler_duration_ms': 10})['status'],'NOT_TESTED')
        data={'evidence_kind':'AWS_LIVE','violation_started_at':'2026-11-16T00:00:00Z',
              'detected_at':'2026-11-16T00:00:02Z','recovery_verified_at':'2026-11-16T00:00:02.1Z'}
        self.assertFalse(timing.assess(data)['target_met'])
        data.update(evidence_kind='MOCK',detected_at='2026-11-16T00:00:00.1Z',recovery_verified_at='2026-11-16T00:00:00.2Z')
        self.assertFalse(timing.assess(data)['aws_target_proven'])

    def test_gitops_has_separate_target_and_immutable_image(self):
        module=load('prepare-gitops-workloads.py')
        with self.assertRaises(ValueError): module.render('alpine:latest','a'*40)
        doc=module.render('123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/team4-test@sha256:'+'a'*64,'b'*40)
        self.assertEqual({x['metadata']['name'] for x in doc['items']}, {'gitops-server','gitops-server-client-only','gitops-client-egress'})
        egress=doc['items'][3]['spec']
        self.assertEqual(egress['podSelector']['matchLabels'], {'app':'client'})
        self.assertEqual(egress['egress'][0]['to'][0]['podSelector']['matchLabels'], {'app':'gitops-server'})
        self.assertEqual(doc['items'][0]['spec']['template']['spec']['securityContext']['runAsUser'],10001)

    def test_github_app_write_access_and_all_repositories_refused(self):
        module=load('configure-gitops-app-auth.py')
        module.validate_installation({'permissions':{'contents':'read','metadata':'read'},'repository_selection':'selected'})
        for record in [
            {'permissions':{'contents':'write'},'repository_selection':'selected'},
            {'permissions':{'contents':'read','issues':'write'},'repository_selection':'selected'},
            {'permissions':{'contents':'read'},'repository_selection':'all'}]:
            with self.assertRaises(ValueError): module.validate_installation(record)
