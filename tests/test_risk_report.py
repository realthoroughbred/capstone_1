"""Synthetic fixtures exercise failure semantics; never presented as scan evidence."""
import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/07-isms-p-risk-report.py'
spec = importlib.util.spec_from_file_location('risk_report', SCRIPT)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def checkov():
    return {'check_type': 'terraform', 'summary': {'passed': 1, 'failed': 0, 'skipped': 0, 'parsing_errors': 0},
            'results': {'passed_checks': [{'check_id': 'PASS'}], 'failed_checks': [], 'skipped_checks': []}}


def trivy():
    return {'SchemaVersion': 2, 'ArtifactType': 'container_image', 'ArtifactName': 'synthetic:test',
            'Metadata': {'OS': {'Family': 'alpine'}, 'ImageID': 'sha256:synthetic'},
            'Results': [{'Target': 'synthetic', 'Packages': [{'Name': 'busybox'}], 'Vulnerabilities': []}]}


class RiskReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def save(self, tool, data, **changes):
        path = self.root / (tool + '.json')
        path.write_text(json.dumps(data), encoding='utf-8')
        meta = {'tool': tool, 'status': 'FINISHED', 'exit_code': 0, 'commit': 'a' * 40,
                'run_id': 'synthetic-test', 'source_tree_sha256': 'tree', 'target': 'test-only',
                'started_at': '2026-11-01T01:00:00Z', 'finished_at': '2026-11-01T01:00:01Z',
                'tool_version': 'test-fixture', 'output_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        meta.update(changes)
        Path(str(path) + '.meta.json').write_text(json.dumps(meta), encoding='utf-8')
        return path

    def test_missing_is_unknown_not_zero(self):
        scan = report.analyze('trivy', self.root / 'absent.json')
        self.assertEqual(scan['state'], 'MISSING')
        self.assertIsNone(scan['counts'])
        self.assertEqual(scan['gate'], 'UNKNOWN')

    def test_failed_scan_without_output_retains_provenance(self):
        path = self.save('trivy', trivy(), exit_code=1)
        path.unlink()
        scan = report.analyze('trivy', path)
        self.assertEqual(scan['state'], 'ERROR')
        self.assertEqual(scan['metadata']['exit_code'], 1)
        self.assertIsNone(scan['counts'])

    def test_skipped_without_output_is_explicit(self):
        path = self.save('trivy', trivy(), status='SKIPPED')
        path.unlink()
        self.assertEqual(report.analyze('trivy', path)['state'], 'SKIPPED')

    def test_checkov_embedded_version_is_used_without_editing_evidence(self):
        data = checkov()
        data['summary']['checkov_version'] = '3.3.29'
        path = self.save('checkov', data, tool_version=None)
        before = Path(str(path) + '.meta.json').read_bytes()
        scan = report.analyze('checkov', path)
        self.assertEqual(scan['state'], 'COMPLETE')
        self.assertEqual(scan['metadata']['tool_version'], '3.3.29')
        self.assertEqual(Path(str(path) + '.meta.json').read_bytes(), before)

    def test_checkov_object_and_list(self):
        for data in [checkov(), [checkov()]]:
            with self.subTest(data=data):
                scan = report.analyze('checkov', self.save('checkov', data))
                self.assertEqual(scan['state'], 'COMPLETE')

    def test_failed_gate_is_a_completed_scan(self):
        data = checkov()
        data['summary']['failed'] = 1
        data['results']['failed_checks'] = [{'check_id': 'CKV_AWS_39', 'resource': 'cluster'}]
        scan = report.analyze('checkov', self.save('checkov', data, exit_code=1))
        self.assertEqual((scan['state'], scan['gate']), ('COMPLETE', 'FAILED'))
        self.assertEqual(scan['findings'][0]['internal_risk']['score'], 15)
        self.assertEqual(scan['findings'][0]['tool_severity'], 'NOT_PROVIDED')
        self.assertFalse(scan['findings'][0]['exception_approved'])

    def test_skips_and_parsing_errors_are_not_passes(self):
        data = checkov()
        data['summary']['skipped'] = 1
        data['results']['skipped_checks'] = [{'check_id': 'SKIP', 'check_result': {'suppress_comment': 'review required'}}]
        self.assertEqual(report.analyze('checkov', self.save('checkov', data))['state'], 'PARTIAL')
        data['summary']['parsing_errors'] = 1
        self.assertEqual(report.analyze('checkov', self.save('checkov', data))['state'], 'ERROR')

    def test_operational_error_with_valid_json_is_not_safe(self):
        for tool, data in [('checkov', checkov()), ('trivy', trivy())]:
            with self.subTest(tool=tool):
                self.assertEqual(report.analyze(tool, self.save(tool, data, exit_code=2))['state'], 'ERROR')

    def test_skipped_metadata_does_not_reuse_stale_counts(self):
        for state in ['SKIPPED', 'NOT_RUN']:
            scan = report.analyze('checkov', self.save('checkov', checkov(), status=state))
            self.assertEqual(scan['state'], state)
            self.assertIsNone(scan['counts'])

    def test_metadata_required_and_hash_bound(self):
        path = self.save('trivy', trivy(), output_sha256='wrong')
        self.assertEqual(report.analyze('trivy', path)['state'], 'UNVERIFIED')
        Path(str(path) + '.meta.json').unlink()
        self.assertEqual(report.analyze('trivy', path)['state'], 'UNVERIFIED')

    def test_commit_and_run_must_match(self):
        path = self.save('checkov', checkov())
        for kwargs in [{'expected_commit': 'b' * 40}, {'expected_run': 'other-run'}]:
            self.assertEqual(report.analyze('checkov', path, **kwargs)['state'], 'UNVERIFIED')

    def test_no_empty_or_malformed_checkov_success(self):
        bad = checkov()
        bad['summary']['failed'] = 1
        for data in [{}, [], {'summary': {}}, bad]:
            self.assertEqual(report.analyze('checkov', self.save('checkov', data))['state'], 'ERROR')

    def test_trivy_requires_os_inventory_not_just_empty_findings(self):
        for data in [{}, {'Results': []}, {**trivy(), 'Results': [{}]}]:
            self.assertEqual(report.analyze('trivy', self.save('trivy', data))['state'], 'ERROR')

    def test_all_trivy_severities_recorded_and_gate_preserved(self):
        data = trivy()
        data['Results'][0]['Vulnerabilities'] = [
            {'VulnerabilityID': 'CVE-TEST-' + s, 'Severity': s, 'PkgName': 'test'}
            for s in ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL', 'UNKNOWN']]
        scan = report.analyze('trivy', self.save('trivy', data))
        self.assertEqual(scan['gate'], 'FAILED')
        self.assertEqual(len(scan['findings']), 5)
        self.assertEqual(scan['counts']['high_critical'], 2)
        self.assertIsNone(scan['findings'][-1]['internal_risk']['score'])

    def test_end_of_life_os_fails(self):
        data = trivy()
        data['Metadata']['OS']['EOSL'] = True
        self.assertEqual(report.analyze('trivy', self.save('trivy', data))['gate'], 'FAILED')

    def test_medium_findings_are_not_described_as_zero_findings(self):
        data = trivy()
        data['Results'][0]['Vulnerabilities'] = [{'VulnerabilityID': 'CVE-TEST', 'Severity': 'MEDIUM'}]
        t = report.analyze('trivy', self.save('trivy', data))
        c = report.analyze('checkov', self.save('checkov', checkov()))
        self.assertEqual(t['gate'], 'PASSED')
        self.assertEqual(report.build_report(c, t)['status'], 'FINDINGS')

    def test_image_digest_mismatch_is_unverified(self):
        path = self.save('trivy', trivy(), image_config_digest='sha256:different')
        self.assertEqual(report.analyze('trivy', path)['state'], 'UNVERIFIED')

    def test_cross_run_provenance_not_combined(self):
        c = report.analyze('checkov', self.save('checkov', checkov()))
        t = report.analyze('trivy', self.save('trivy', trivy(), run_id='different'))
        merged = report.build_report(c, t)
        self.assertEqual(merged['status'], 'INCOMPLETE')
        self.assertIn('run_id', merged['issues'][0])

    def test_cli_missing_inputs_writes_incomplete_and_never_overwrites(self):
        out = self.root / 'report'
        cmd = [sys.executable, str(SCRIPT), '--checkov', str(self.root/'missing-c'),
               '--trivy', str(self.root/'missing-t'), '--output-dir', str(out)]
        first = subprocess.run(cmd, capture_output=True)
        self.assertEqual(first.returncode, 2)
        before = (out/'isms-p-risk-report.md').read_bytes()
        second = subprocess.run(cmd, capture_output=True)
        self.assertEqual(second.returncode, 2)
        self.assertEqual(before, (out/'isms-p-risk-report.md').read_bytes())
        self.assertIn('INCOMPLETE', before.decode('utf-8'))


if __name__ == '__main__':
    unittest.main()
