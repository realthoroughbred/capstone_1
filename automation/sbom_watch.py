"""Compare a complete SBOM scan with a digest-scoped ledger; duplicates still gate."""
import hashlib
import json
import re


def compare(scan, image_digest, previous):
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image_digest):
        raise ValueError('Valid image digest required')
    if not isinstance(previous, dict) or previous.get('schema_version') != 1 or not isinstance(previous.get('images'), dict):
        raise ValueError('Invalid previous ledger')
    if scan.get('SchemaVersion') != 2 or scan.get('ArtifactType') != 'cyclonedx':
        raise ValueError('Expected a Trivy CycloneDX SBOM scan')
    results = scan.get('Results')
    if not isinstance(results, list) or not results:
        raise ValueError('SBOM scan coverage missing')
    current = {}
    for result in results:
        if not isinstance(result, dict):
            raise ValueError('Invalid scan result')
        findings = result.get('Vulnerabilities', [])
        if findings is None:
            findings = []
        if not isinstance(findings, list):
            raise ValueError('Invalid vulnerability collection')
        for finding in findings:
            if not isinstance(finding, dict) or not all(isinstance(finding.get(k), str) and finding[k] for k in ['VulnerabilityID', 'PkgName', 'InstalledVersion', 'Severity']):
                raise ValueError('Incomplete vulnerability identity')
            if finding['Severity'] not in {'UNKNOWN', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'}:
                raise ValueError('Unknown severity vocabulary')
            identity = [image_digest, result.get('Target'), finding['VulnerabilityID'], finding['PkgName'], finding['InstalledVersion']]
            key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
            current[key] = {k: finding.get(k) for k in ['VulnerabilityID', 'PkgName', 'InstalledVersion', 'FixedVersion', 'Severity']}
    old = previous['images'].get(image_digest, {})
    if not isinstance(old, dict):
        raise ValueError('Invalid image ledger')
    new, recurring, resolved = set(current) - set(old), set(current) & set(old), set(old) - set(current)
    ledger = {'schema_version': 1, 'images': {**previous['images'], image_digest: current}}
    blocked = any(f['Severity'] in {'HIGH', 'CRITICAL'} for f in current.values())
    return {'status': 'COMPLETE', 'image_digest': image_digest, 'deployment_gate': 'BLOCKED' if blocked else 'PASSED_IN_SCANNED_SCOPE',
            'new': {k: current[k] for k in sorted(new)}, 'recurring': {k: current[k] for k in sorted(recurring)},
            'resolved': {k: old[k] for k in sorted(resolved)},
            'follow_up': 'HIGH/CRITICAL: block deployment, investigate authoritative Inspector finding, prepare and separately approve a scanned/signed replacement; never invent a safe image.',
            'ledger': ledger}
