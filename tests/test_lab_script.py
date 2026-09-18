from __future__ import annotations

import json
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


def test_logs_reject_state_that_points_outside_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    scripts = project / "scripts"
    runtime = project / ".local" / "runtime"
    scripts.mkdir(parents=True)
    runtime.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "lab.ps1", scripts / "lab.ps1")

    outside = tmp_path / "outside.log"
    outside.write_text("SECRET_MARKER\n", encoding="utf-8")
    state = {
        "schema_version": 1,
        "pid": 1,
        "start_filetime_utc": 1,
        "executable": str(project / ".venv" / "Scripts" / "python.exe"),
        "project_root": str(project),
        "port": 8000,
        "stdout_log": str(outside),
        "stderr_log": str(project / ".local" / "logs" / "lelab-fixture.stderr.log"),
    }
    (runtime / "lelab-process.json").write_text(json.dumps(state), encoding="utf-8")

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(scripts / "lab.ps1"),
            "logs",
        ],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "SECRET_MARKER" not in result.stdout
    assert "SECRET_MARKER" not in result.stderr
    assert "failed ownership validation" in result.stderr


def test_logs_accept_state_recorded_with_windows_base_python(tmp_path: Path) -> None:
    project = tmp_path / "project"
    scripts = project / "scripts"
    runtime = project / ".local" / "runtime"
    logs = project / ".local" / "logs"
    scripts.mkdir(parents=True)
    runtime.mkdir(parents=True)
    logs.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "lab.ps1", scripts / "lab.ps1")

    stdout_log = logs / "lelab-fixture.stdout.log"
    stderr_log = logs / "lelab-fixture.stderr.log"
    stdout_log.write_text("BASE_PYTHON_STATE_OK\n", encoding="utf-8")
    stderr_log.write_text("", encoding="utf-8")
    state = {
        "schema_version": 1,
        "pid": 1,
        "start_filetime_utc": 1,
        "executable": str(tmp_path / "python-install" / "python.exe"),
        "project_root": str(project),
        "port": 8000,
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
    }
    (runtime / "lelab-process.json").write_text(json.dumps(state), encoding="utf-8")

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(scripts / "lab.ps1"),
            "logs",
        ],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "BASE_PYTHON_STATE_OK" in result.stdout


def test_logs_reject_link_inside_project_that_targets_external_file(tmp_path: Path) -> None:
    project = tmp_path / "project"
    scripts = project / "scripts"
    runtime = project / ".local" / "runtime"
    logs = project / ".local" / "logs"
    scripts.mkdir(parents=True)
    runtime.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "lab.ps1", scripts / "lab.ps1")

    outside_logs = tmp_path / "outside-logs"
    outside_logs.mkdir()
    outside = outside_logs / "lelab-fixture.stdout.log"
    outside.write_text("SECRET_MARKER\n", encoding="utf-8")
    _make_directory_link(logs, outside_logs)
    linked_log = logs / "lelab-fixture.stdout.log"
    state = {
        "schema_version": 1,
        "pid": 1,
        "start_filetime_utc": 1,
        "executable": str(project / ".venv" / "Scripts" / "python.exe"),
        "project_root": str(project),
        "port": 8000,
        "stdout_log": str(linked_log),
        "stderr_log": str(logs / "lelab-fixture.stderr.log"),
    }
    (runtime / "lelab-process.json").write_text(json.dumps(state), encoding="utf-8")

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(scripts / "lab.ps1"),
            "logs",
        ],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "SECRET_MARKER" not in result.stdout
    assert "SECRET_MARKER" not in result.stderr
    assert "reparse point" in result.stderr
