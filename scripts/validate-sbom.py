"""Validate CycloneDX schema and bind the local SBOM to the Docker config digest."""
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

import jsonschema
from referencing import Registry, Resource


def validate(document):
    version = document.get('specVersion')
    if document.get('bomFormat') != 'CycloneDX' or version not in {'1.5', '1.6', '1.7'}:
        raise ValueError('unsupported CycloneDX format/version')
    if not document.get('components'):
        raise ValueError('SBOM contains no components; do not count an empty catalog as verified')
    def retrieve(uri):
        name = uri.rsplit('/', 1)[-1]
        if name not in {f'bom-{version}.schema.json', 'spdx.schema.json', 'jsf-0.82.schema.json'}:
            raise ValueError('unexpected external schema reference')
        revision = 'ad83dae28b236b8760286399da4daba77592de86'
        url = 'https://raw.githubusercontent.com/CycloneDX/specification/' + revision + '/schema/' + name
        request = urllib.request.Request(url, headers={'User-Agent': 'team4-sbom-validator'})
        with urllib.request.urlopen(request, timeout=30) as response:
            content = json.load(response)
        return Resource.from_contents(content)
    uri = f'http://cyclonedx.org/schema/bom-{version}.schema.json'
    schema = retrieve(uri).contents
    validator = jsonschema.validators.validator_for(schema)
    validator.check_schema(schema)
    validator(schema, registry=Registry(retrieve=retrieve)).validate(document)


if __name__ == '__main__':
    sbom, digest_file, output = map(Path, sys.argv[1:])
    document = json.loads(sbom.read_text())
    validate(document)
    digest = digest_file.read_text().strip()
    if not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
        raise ValueError('invalid image config digest')
    Path(output).write_text(json.dumps({
        'image_config_digest': digest,
        'registry_manifest_digest': None,
        'sbom_sha256': hashlib.sha256(sbom.read_bytes()).hexdigest(),
        'component_count': len(document['components']),
        'schema_version': document['specVersion'],
        'note': 'Config digest is not an OCI registry manifest digest. Registry binding occurs after push.'
    }, indent=2) + '\n')
