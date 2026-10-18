"""Verify that the precise SBOM bytes are bound to the scanned image config."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def verify_binding(sbom_path, link_path, config_digest):
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', config_digest):
        raise ValueError('Invalid image config digest')
    sbom_bytes = Path(sbom_path).read_bytes()
    link = json.loads(Path(link_path).read_text(encoding='utf-8'))
    if not isinstance(link, dict) or link.get('image_config_digest') != config_digest:
        raise ValueError('SBOM binding belongs to a different image config')
    if link.get('sbom_sha256') != hashlib.sha256(sbom_bytes).hexdigest():
        raise ValueError('SBOM bytes changed after validation')
    sbom = json.loads(sbom_bytes)
    if not isinstance(sbom, dict) or sbom.get('bomFormat') != 'CycloneDX':
        raise ValueError('Bound document is not a CycloneDX SBOM')
    components = sbom.get('components')
    if not isinstance(components, list) or not components:
        raise ValueError('Bound SBOM has no component inventory')
    if type(link.get('component_count')) is not int or link['component_count'] != len(components):
        raise ValueError('SBOM component count differs from its validation record')
    if link.get('schema_version') != sbom.get('specVersion'):
        raise ValueError('SBOM schema version differs from its validation record')
    return link


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sbom')
    parser.add_argument('binding')
    parser.add_argument('config_digest')
    args = parser.parse_args()
    try:
        verify_binding(args.sbom, args.binding, args.config_digest)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')
    print('PASS: exact SBOM bytes and inventory match the scanned image config binding.')
