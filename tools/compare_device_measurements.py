#!/usr/bin/env python3
"""Compare imported device observations with saved Omada timelines offline."""
from pathlib import Path
import sys

PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.device_measurement_compare import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
