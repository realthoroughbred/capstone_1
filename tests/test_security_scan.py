"""Exercise the evidence wrapper with synthetic executables, never cloud APIs."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/security_scan.py'


class ScanRecorderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'checkov.json'

    def command(self, code):
        return [sys.executable, str(SCRIPT), '--tool', 'checkov', '--output', str(self.path),
                '--stdout-json', '--target', 'synthetic-fixture', '--run-id', 'test-only',
                '--', sys.executable, '-c', code]

    def test_preserves_finding_exit_code_and_embedded_version(self):
        result = subprocess.run(self.command('import json,sys; print(json.dumps({"summary":{"checkov_version":"test-version"}})); sys.exit(1)'),
                                cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 1)
        meta = json.loads(Path(str(self.path) + '.meta.json').read_text())
        self.assertEqual(meta['status'], 'FINISHED')
        self.assertEqual(meta['exit_code'], 1)
        self.assertEqual(meta['tool_version'], 'test-version')
        self.assertEqual(meta['output_sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertTrue(meta['started_at'] and meta['finished_at'] and meta['commit'])

    def test_refuses_existing_result_without_overwriting_it(self):
        self.path.write_text('prior evidence')
        result = subprocess.run(self.command('print("unexpected")'), cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.path.read_text(), 'prior evidence')

    def test_operational_stderr_and_failure_retained(self):
        result = subprocess.run(self.command('import sys; print("synthetic scanner outage", file=sys.stderr); sys.exit(2)'),
                                cwd=ROOT, capture_output=True)
        self.assertEqual(result.returncode, 2)
        meta = json.loads(Path(str(self.path) + '.meta.json').read_text())
        self.assertEqual(meta['exit_code'], 2)
        self.assertIsNone(meta['tool_version'])
        self.assertIn('synthetic scanner outage', Path(str(self.path) + '.stderr.txt').read_text())


if __name__ == '__main__':
    unittest.main()
