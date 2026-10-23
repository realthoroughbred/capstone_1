#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p downloads/python .tools/bin
version=0.9.4
file=uv-x86_64-unknown-linux-gnu.tar.gz
base="https://github.com/astral-sh/uv/releases/download/$version"
curl -fsSL --retry 3 "$base/$file" -o "downloads/python/$file"
curl -fsSL --retry 3 "$base/$file.sha256" -o "downloads/python/$file.sha256"
(cd downloads/python && sha256sum --check "$file.sha256")
tar -xzf "downloads/python/$file" -C .tools/bin --strip-components=1 uv-x86_64-unknown-linux-gnu/uv
export UV_PYTHON_INSTALL_DIR="$PWD/.tools/python"
export UV_CACHE_DIR="$PWD/.tools/uv-cache"
.tools/bin/uv python install 3.12
.tools/bin/uv venv --python 3.12 .venv-ci
.tools/bin/uv pip install --python .venv-ci/bin/python -r requirements-dev.txt
