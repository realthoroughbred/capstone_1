import copy
import unittest
from automation.sbom_watch import compare


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.digest = 'sha256:'+'a'*64
        self.scan = {'SchemaVersion': 2, 'ArtifactType': 'cyclonedx', 'Results': [{'Target': 'alpine', 'Vulnerabilities': [
            {'VulnerabilityID': 'CVE-SYNTHETIC', 'PkgName': 'test', 'InstalledVersion': '1', 'Severity': 'HIGH'}]}]}
        self.empty = {'schema_version': 1, 'images': {}}

    def test_new_then_duplicate_still_blocks_and_resolved_is_tracked(self):
        first = compare(self.scan, self.digest, self.empty)
        self.assertEqual(len(first['new']), 1)
        second = compare(self.scan, self.digest, first['ledger'])
        self.assertEqual(len(second['new']), 0)
        self.assertEqual(len(second['recurring']), 1)
        self.assertEqual(second['deployment_gate'], 'BLOCKED')
        self.scan['Results'][0]['Vulnerabilities'] = []
        third = compare(self.scan, self.digest, second['ledger'])
        self.assertEqual(len(third['resolved']), 1)

    def test_image_identity_separates_ledgers(self):
        first = compare(self.scan, self.digest, self.empty)
        second = compare(self.scan, 'sha256:'+'b'*64, first['ledger'])
        self.assertEqual(len(second['new']), 1)
        self.assertEqual(len(second['ledger']['images']), 2)

    def test_missing_and_malformed_scan_never_resolves_findings(self):
        for value in [None, {}, '', False]:
            bad = copy.deepcopy(self.scan)
            bad['Results'] = value
            with self.assertRaises(ValueError): compare(bad, self.digest, self.empty)
        self.scan['Results'][0]['Vulnerabilities'] = {}
        with self.assertRaises(ValueError): compare(self.scan, self.digest, self.empty)
