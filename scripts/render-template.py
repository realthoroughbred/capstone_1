"""Expand only ${NAME} from environment, leaving Kyverno {{ expressions }} intact."""
import os
import pathlib
import re
import sys

text = pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')
def replace(match):
    value = os.environ.get(match[1])
    if not value or '\n' in value or '\r' in value:
        raise SystemExit(f'Missing or multiline template variable: {match[1]}')
    return value
sys.stdout.write(re.sub(r'\$\{([A-Z][A-Z0-9_]*)\}', replace, text))
