#!/usr/bin/env python3
"""清空 data/ 目录下的所有内容，但保留 data/ 目录本身。"""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from app.cleanup import clear_all_data


if __name__ == "__main__":
    raise SystemExit(clear_all_data())
