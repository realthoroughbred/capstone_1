"""Regression for the live test's mutated positive control (no Rego reimplementation)."""
import importlib.util
import unittest
import json
import subprocess
from pathlib import Path

spec = importlib.util.spec_from_file_location('admission_cases', Path(__file__).parents[1] / 'scripts/test-gatekeeper-local.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AdmissionFixtureTests(unittest.TestCase):
    def test_query_errors_are_failed_results(self):
        bad = subprocess.CompletedProcess([], 1, '', 'Forbidden')
        self.assertFalse(module.pod_absent(bad, 'rejected'))
        for kind in ['constrainttemplate', 'team4nonroot']:
            self.assertEqual(module.controller_result(bad, kind)['result'], 'FAIL')

    def test_status_requires_current_generation_and_enforcement(self):
        doc = {'metadata': {'generation': 2}, 'status': {'created': True,
               'byPod': [{'enforced': True, 'observedGeneration': 2}]}}
        response = lambda: subprocess.CompletedProcess([], 0, json.dumps(doc), '')
        self.assertEqual(module.controller_result(response(), 'team4nonroot')['result'], 'PASS')
        doc['status']['byPod'][0]['observedGeneration'] = 1
        self.assertEqual(module.controller_result(response(), 'team4nonroot')['result'], 'FAIL')
        for value in ['{}', 'not-json', '{"items":[{}]}']:
            self.assertFalse(module.pod_absent(subprocess.CompletedProcess([], 0, value, ''), 'rejected'))

    def test_kyverno_positive_control_is_not_changed_by_negative_case(self):
        cases = {name: obj for name, obj, _, _ in module.cases('synthetic:test')}
        positive = cases['kyverno-valid']['spec']['containers'][0]['securityContext']
        negative = cases['kyverno-writable-rootfs']['spec']['containers'][0]['securityContext']
        self.assertIs(positive['readOnlyRootFilesystem'], True)
        self.assertIs(negative['readOnlyRootFilesystem'], False)
        negative['runAsUser'] = 0
        self.assertNotIn('runAsUser', positive)


if __name__ == '__main__':
    unittest.main()
