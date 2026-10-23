import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.verify_sbom_binding import verify_binding


class SbomBindingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.sbom = Path(self.directory.name) / 'sbom.json'
        self.link = Path(self.directory.name) / 'binding.json'
        self.digest = 'sha256:' + 'a' * 64
        self.document = {'bomFormat': 'CycloneDX', 'specVersion': '1.6',
                         'components': [{'name': 'busybox', 'version': '1.37.0', 'type': 'application'}]}
        self.write_fixture()

    def write_fixture(self):
        self.sbom.write_text(json.dumps(self.document), encoding='utf-8')
        self.binding = {'image_config_digest': self.digest,
                        'sbom_sha256': hashlib.sha256(self.sbom.read_bytes()).hexdigest(),
                        'component_count': len(self.document['components']), 'schema_version': '1.6'}
        self.link.write_text(json.dumps(self.binding), encoding='utf-8')

    def test_exact_validated_sbom_is_accepted(self):
        self.assertEqual(verify_binding(self.sbom, self.link, self.digest), self.binding)

    def test_modified_sbom_is_rejected_even_if_still_valid_json(self):
        self.document['components'][0]['version'] = 'different-image-package'
        self.sbom.write_text(json.dumps(self.document), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'bytes changed'):
            verify_binding(self.sbom, self.link, self.digest)

    def test_binding_from_another_image_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'different image config'):
            verify_binding(self.sbom, self.link, 'sha256:' + 'b' * 64)

    def test_empty_inventory_cannot_be_accepted_by_rehashing(self):
        self.document['components'] = []
        self.write_fixture()
        with self.assertRaisesRegex(ValueError, 'no component inventory'):
            verify_binding(self.sbom, self.link, self.digest)

    def test_inconsistent_validation_metadata_is_rejected(self):
        self.binding['component_count'] += 1
        self.link.write_text(json.dumps(self.binding), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'component count'):
            verify_binding(self.sbom, self.link, self.digest)


if __name__ == '__main__':
    unittest.main()
