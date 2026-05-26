#!/usr/bin/env bash
set -euo pipefail
export OCR_LANG=${OCR_LANG:-HanS+eng}
export STORAGE_DIR=${STORAGE_DIR:-./storage}
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --reload
