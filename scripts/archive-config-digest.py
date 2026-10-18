"""Docker's containerd image-store ID can be a manifest digest; hash actual OCI config bytes."""
import hashlib
import json
import sys
import tarfile

with tarfile.open(sys.argv[1]) as archive:
    manifest = json.load(archive.extractfile('manifest.json'))
    if len(manifest) != 1:
        raise ValueError('expected a single-platform image archive')
    config = archive.extractfile(manifest[0]['Config']).read()
    print('sha256:' + hashlib.sha256(config).hexdigest())
