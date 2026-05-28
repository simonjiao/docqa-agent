#!/usr/bin/env bash
set -euo pipefail
if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source ".env"
  set +a
fi
export OCR_LANG=${OCR_LANG:-chi_sim+eng}
export STORAGE_DIR=${STORAGE_DIR:-./storage}
if [[ -x ".venv/bin/uvicorn" ]]; then
  UVICORN=".venv/bin/uvicorn"
else
  UVICORN="uvicorn"
fi
exec "$UVICORN" app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
