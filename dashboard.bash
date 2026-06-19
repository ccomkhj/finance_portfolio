#!/usr/bin/env bash
# Launch the Streamlit dashboard against your PRIVATE data (data/private),
# not the public synthetic demo in data/. Run from anywhere:  ./dashboard.bash
set -euo pipefail
cd "$(dirname "$0")"
export PORTFOLIO_DATA_DIR="${PORTFOLIO_DATA_DIR:-data/private}"
exec uv run portfolio dashboard "$@"
