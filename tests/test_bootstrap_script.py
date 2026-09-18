from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _make_directory_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except OSError:
        pass
    environment = os.environ.copy()
    environment["LELAB_TEST_LINK"] = str(link)
    environment["LELAB_TEST_TARGET"] = str(target)
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-Command",
            (
                "New-Item -ItemType Junction -Path $env:LELAB_TEST_LINK "
                "-Target $env:LELAB_TEST_TARGET | Out-Null"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if result.returncode != 0:
        pytest.skip(f"directory link unavailable: {result.stderr}")


def test_bootstrap_rejects_reparse_in_manifest_path(tmp_path: Path) -> None:
    project = tmp_path / "project"
    tools = project / "tools"
    external = tmp_path / "external-config"
    tools.mkdir(parents=True)
    external.mkdir()
    shutil.copy2(ROOT / "tools" / "bootstrap_upstream.ps1", tools / "bootstrap_upstream.ps1")
    (external / "upstream-pins.json").write_text("{}", encoding="utf-8")
    _make_directory_link(project / "configs", external)

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tools / "bootstrap_upstream.ps1"),
        ],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "reparse point" in result.stderr
    assert "Unable to read the authoritative upstream pin manifest" not in result.stderr
