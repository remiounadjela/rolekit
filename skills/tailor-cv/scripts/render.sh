#!/usr/bin/env bash
# Set up private PDF dependencies automatically; no uv or global pip is required.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
for PYTHON_CANDIDATE in "${ROLEKIT_PYTHON:-python3}" python; do
  if "$PYTHON_CANDIDATE" -c 'import sys; sys.exit(sys.version_info < (3, 10))' >/dev/null 2>&1; then
    exec "$PYTHON_CANDIDATE" "$SCRIPT_DIR/render_auto.py" "$@"
  fi
done
echo 'RoleKit needs a host Python 3.10+ runtime. The agent can set ROLEKIT_PYTHON to its bundled Python.' >&2
exit 1
