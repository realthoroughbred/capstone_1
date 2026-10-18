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
