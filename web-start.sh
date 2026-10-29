#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
exec python -m streamlit run app.py \
  --server.address 0.0.0.0 \
  --server.port "${PORT:-8501}" \
  --server.headless true \
  --server.maxUploadSize 20 \
  --browser.gatherUsageStats false
