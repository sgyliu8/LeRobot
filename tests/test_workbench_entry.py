"""Portable entry checks without importing LeLab or touching its job registry."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("runtime_check", ROOT / "tools/runtime_check.py")
runtime_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime_check)


def test_install_receipt_rejects_changed_code_and_lock(tmp_path, monkeypatch, capsys):
    files = {
        "configs/upstream-pins.json": json.dumps({
            "patch_set": ["patches/fixed.patch"],
            "lelab": {"commit": "fixture"}, "lerobot": {"commit": "fixture"},
        }),
        "patches/fixed.patch": "fixed patch", "uv.lock": "locked",
        "_vendor/lelab/lelab/__init__.py": "# fixture",
        "_vendor/lelab/frontend/dist/index.html": "fixture",
        "so101_lab/__init__.py": "# local adapter",
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(runtime_check, "ROOT", tmp_path)
    monkeypatch.setattr(runtime_check, "check_environment", lambda _: [])
    monkeypatch.setattr(sys, "argv", ["check"])
    assert runtime_check.main() == 2
    monkeypatch.setattr(sys, "argv", ["check", "--record"])
    assert runtime_check.main() == 0
    monkeypatch.setattr(sys, "argv", ["check"])
    assert runtime_check.main() == 0
    (tmp_path / "uv.lock").write_text("changed", encoding="utf-8")
    assert runtime_check.main() == 2
    assert "lock_sha256" in capsys.readouterr().out
    (tmp_path / "uv.lock").write_text("locked", encoding="utf-8")
    (tmp_path / "so101_lab/__init__.py").write_text("# changed", encoding="utf-8")
    assert runtime_check.main() == 2
    assert "source_sha256" in capsys.readouterr().out


def test_environment_does_not_accept_another_venv(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "foreign"))
    # Keep all other real package checks read-only, with the actual checkout.
    assert any("another folder" in error for error in runtime_check.check_environment(ROOT))


@pytest.mark.skipif(os.name != "nt", reason="Windows entry point")
def test_maintenance_lock_is_exclusive_and_reusable(tmp_path):
    script = ROOT / "scripts/maintenance.ps1"
    fixture = tmp_path / "space Unicode 空间"
    fixture.mkdir()
    env = {**os.environ, "SO101_FIXTURE_ROOT": str(fixture), "SO101_LOCK_SCRIPT": str(script)}
    result = subprocess.run([
        "powershell.exe", "-NoProfile", "-Command",
        (". $env:SO101_LOCK_SCRIPT; $first = Enter-WorkbenchLock $env:SO101_FIXTURE_ROOT; "
        "$denied = $false; try { $second = Enter-WorkbenchLock $env:SO101_FIXTURE_ROOT } "
        "catch { $denied = $true }; $first.Dispose(); if (-not $denied) { exit 1 }; "
        "$third = Enter-WorkbenchLock $env:SO101_FIXTURE_ROOT; $third.Dispose(); exit 0"),
    ], env=env, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr
