#!/usr/bin/env bash
# delegation-core installer for Linux and macOS.
#
# Only finds a Python 3.11+ and hands over to install.py, which does the rest
# (system packages, venv, backup, pip, post-install) the same way on every
# platform. Before 2026-10-06 that logic lived here and again in install.bat,
# and the two copies had drifted apart.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for cmd in python3.13 python3.12 python3.11 python3; do
    if command -v "$cmd" >/dev/null 2>&1 &&
       [ "$("$cmd" -c 'import sys; print(sys.version_info >= (3, 11))' 2>/dev/null)" = "True" ]; then
        exec "$cmd" "$SCRIPT_DIR/install.py" "$@"
    fi
done

echo ""
echo "ERROR: Python 3.11+ is required."
if [ "$(uname -s)" = "Darwin" ]; then
    echo "Install: https://www.python.org/downloads/  or  brew install python@3.11"
else
    echo "Install: sudo apt install python3.11  (Ubuntu/Debian)"
fi
exit 1
