#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
[[ -f .env ]] || cp .env.example .env
python3 -c 'import sys; assert (3,11) <= sys.version_info[:2] < (3,14), "Please use Python 3.11-3.13"'
[[ -d .venv ]] || python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
if [[ "${1:-}" == "--demo" ]]; then
  .venv/bin/python -m app.cli init --demo
else
  .venv/bin/python -m app.cli init
fi
printf '\nOpen http://127.0.0.1:8000 — Ctrl+C stops the service.\n'
exec .venv/bin/python -m maintenance.supervisor
