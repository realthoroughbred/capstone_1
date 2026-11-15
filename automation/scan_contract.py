"""One strict Trivy inventory contract for reporting and deployment gates."""
import re


def validate_inventory(report, *, require_identity=False):
    if not isinstance(report, dict):
        raise ValueError('Trivy document must be an object')
    metadata = report.get('Metadata')
    if not isinstance(metadata, dict) or not isinstance(metadata.get('OS'), dict):
        raise ValueError('Trivy OS metadata missing')
    if not isinstance(metadata['OS'].get('Family'), str) or not metadata['OS']['Family']:
        raise ValueError('Trivy OS family missing')
    results = report.get('Results')
    if not isinstance(results, list) or not results:
        raise ValueError('Trivy results must be a nonempty list')
    count = 0
    for result in results:
        if not isinstance(result, dict):
            raise ValueError('Trivy result must be an object')
        for field in ('Packages', 'Vulnerabilities'):
            values = result.get(field, [])
            # Trivy may omit or encode a nil vulnerability slice as null.
            if field == 'Vulnerabilities' and values is None:
                values = []
            if not isinstance(values, list) or any(not isinstance(v, dict) for v in values):
                raise ValueError(f'{field} must contain objects in a list')
            if field == 'Packages':
                if any(not isinstance(p.get('Name'), str) or not p['Name'] for p in values):
                    raise ValueError('Package name missing')
                count += len(values)
            else:
                if any(v.get('Severity', 'UNKNOWN') not in {'UNKNOWN', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'} for v in values):
                    raise ValueError('Unsupported vulnerability severity')
    if count == 0:
        raise ValueError('Trivy package inventory missing; use --list-all-pkgs')
    if require_identity:
        if report.get('SchemaVersion') != 2 or report.get('ArtifactType') != 'container_image':
            raise ValueError('Expected Trivy schema 2 container_image')
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', metadata.get('ImageID') or ''):
            raise ValueError('Valid image config digest missing')
    return count
