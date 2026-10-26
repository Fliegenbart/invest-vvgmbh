#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
if ! command -v python3 >/dev/null 2>&1; then
  echo 'Python 3.11 oder neuer fehlt. Installation: https://www.python.org/downloads/macos/'
  read -r -p 'Enter zum Schließen ...' _; exit 1
fi
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)'; then
  echo 'Python 3.11 oder neuer wird benötigt.'; read -r -p 'Enter ...' _; exit 1
fi
if [ ! -d .venv ]; then python3 -m venv .venv; fi
if ! .venv/bin/python -c 'import fastapi,uvicorn,httpx,pydantic,boto3,bs4,pypdf,dotenv' 2>/dev/null; then
  echo 'Installiere die Python-Abhängigkeiten in eine isolierte lokale Umgebung ...'
  .venv/bin/python -m pip install -r requirements.txt
fi
exec .venv/bin/python start.py
