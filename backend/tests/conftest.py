"""Test environment.

The backend reads its storage paths at import time, so the environment must be
configured before any ``backend`` module is imported. Pytest loads conftest
files before collecting test modules, which makes this the safe place.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="edgeguard-tests-"))
os.environ["EDGEGUARD_DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["EDGEGUARD_DB_PATH"] = str(TEST_DATA_DIR / "edgeguard-test.sqlite3")
os.environ["EDGEGUARD_SYNC_JOBS"] = "1"

atexit.register(lambda: shutil.rmtree(TEST_DATA_DIR, ignore_errors=True))
