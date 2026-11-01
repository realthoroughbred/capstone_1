"""Regression for the live test's mutated positive control (no Rego reimplementation)."""
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('admission_cases', Path(__file__).parents[1] / 'scripts/test-gatekeeper-local.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AdmissionFixtureTests(unittest.TestCase):
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
