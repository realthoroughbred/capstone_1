import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('evidence', Path(__file__).parents[1] / 'scripts/evidence_report.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {'source': 'official', 'scope': 'technical only', 'controls': {'2.6.1': 'network'},
                        'policies': {'NET-001': {'name': 'SSH', 'controls': ['2.6.1']}}}

    def test_pass_without_evidence_rejected(self):
        with self.assertRaises(ValueError):
            module.generate(self.mapping, [{'policy_id': 'NET-001', 'scope': 'aws', 'result': 'PASS'}], Path('.'))

    def test_simulated_scope_preserved_and_hash_recorded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'test.log').write_text('mock API passed')
            report = module.generate(self.mapping, [{'policy_id': 'NET-001', 'scope': 'simulated', 'result': 'PASS', 'evidence': ['test.log']}], root)
            self.assertEqual(report['records'][0]['scope'], 'simulated')
            self.assertEqual(len(report['records'][0]['evidence'][0]['sha256']), 64)
            self.assertFalse(report['records'][0]['remediation_executed'])

    def test_missing_and_traversal_rejected(self):
        for evidence in ['missing.log', '../outside']:
            with self.assertRaises(ValueError):
                module.generate(self.mapping, [{'policy_id': 'NET-001', 'scope': 'static', 'result': 'PASS', 'evidence': [evidence]}], Path('.'))

    def test_blocked_requires_no_fake_evidence(self):
        report = module.generate(self.mapping, [{'policy_id': 'NET-001', 'scope': 'aws', 'result': 'BLOCKED'}], Path('.'))
        self.assertEqual(report['records'][0]['revalidation'], 'NOT_TESTED')
