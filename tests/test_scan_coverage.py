import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('coverage_gate', Path(__file__).parents[1] / 'scripts/check-image-report.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ScanCoverageTests(unittest.TestCase):
    def test_empty_scan_is_not_clean(self):
        with self.assertRaises(ValueError):
            module.validate({'Results': []})

    def test_packages_required(self):
        with self.assertRaises(ValueError):
            module.validate({'Metadata': {'OS': {'Family': 'alpine'}}, 'Results': [{}]})

    def test_supported_inventory(self):
        self.assertEqual(module.validate({'Metadata': {'OS': {'Family': 'alpine'}}, 'Results': [{'Packages': [{'Name': 'busybox'}]}]}), 1)

    def test_json_gate_rejects_high_and_critical(self):
        for severity, expected in [('HIGH', 1), ('CRITICAL', 1), ('MEDIUM', 0)]:
            report = {'Metadata': {'OS': {'Family': 'alpine'}}, 'Results': [
                {'Packages': [{'Name': 'busybox'}], 'Vulnerabilities': [{'Severity': severity}]}]}
            self.assertEqual(module.enforce(report), expected)

    def test_json_gate_still_rejects_absent_inventory(self):
        with self.assertRaises(ValueError):
            module.enforce({'Results': []})
