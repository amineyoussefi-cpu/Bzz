#!/usr/bin/env bash
# Install (first run) and start the OpenJev decision service on macOS. Usage: ./decision/start.sh
# Reads ../.env if present; every OPENJEV_* variable is optional (see .env.example).
set -euo pipefail
cd "$(dirname "$0")"

if [ -f ../.env ]; then set -a; . ../.env; set +a; fi
PYTHON="${PYTHON:-python3}"

if [ ! -x .venv/bin/python ]; then
  echo "Creating the decision service environment (decision/.venv)..."
  "$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 10))' || { echo "Python 3.10+ required"; exit 1; }
  "$PYTHON" -m venv .venv
fi
# pip is a no-op once everything is installed
.venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt

exec .venv/bin/python service.py
