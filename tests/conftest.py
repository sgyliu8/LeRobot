"""Project test isolation established before any LeLab module is imported."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TEST_JOB_ROOT = Path(tempfile.mkdtemp(prefix="so101-lab-project-tests-")) / "jobs"
os.environ["LELAB_OUTPUT_ROOT"] = str(_TEST_JOB_ROOT)
