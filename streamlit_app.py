from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("PORTFOLIO_READ_ONLY", "1")

from app import main  # noqa: E402


main()
