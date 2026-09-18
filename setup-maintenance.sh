#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ -x .venv/bin/python ]] || { echo 'Run start.sh once before installing optional maintenance.'; exit 1; }
command -v git >/dev/null || { echo 'Install Git first.'; exit 1; }
command -v docker >/dev/null || { echo 'Install and start Docker with Linux containers first.'; exit 1; }
docker info >/dev/null
.venv/bin/python -m pip install -r requirements-maintenance.txt
# Build only from the original reviewed checkout, NEVER from an AI release.
docker build -f maintenance/Dockerfile.test -t dealerdesk-tests:0.2 .
printf '\nOptional dependencies ready. Configure .env using docs/MAINTENANCE.md, then restart start.sh.\n'
