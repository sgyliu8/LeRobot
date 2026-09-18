from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_docs", ROOT / "tools" / "validate_docs.py")
assert SPEC and SPEC.loader
validate_docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_docs)


@pytest.fixture()
def public_tree(tmp_path: Path) -> Path:
    for relative in validate_docs.REQUIRED_FILES:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return tmp_path


def _read_json(root: Path, relative: str) -> dict:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def _write_json(root: Path, relative: str, value: dict) -> None:
    (root / relative).write_text(json.dumps(value), encoding="utf-8")


def test_public_tree_passes(public_tree: Path) -> None:
    assert validate_docs.validate(public_tree) == []


def test_missing_required_document_fails(public_tree: Path) -> None:
    (public_tree / "docs" / "SAFETY.md").unlink()
    assert any("missing required file" in error for error in validate_docs.validate(public_tree))


def test_broken_relative_link_fails(public_tree: Path) -> None:
    readme = public_tree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\n[missing](docs/NOPE.md)\n", encoding="utf-8")
    assert any("broken relative link" in error for error in validate_docs.validate(public_tree))


def test_absolute_windows_path_fails(public_tree: Path) -> None:
    readme = public_tree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nC:\\private\\file\n", encoding="utf-8")
    assert any("Windows absolute path" in error for error in validate_docs.validate(public_tree))


def test_internal_workflow_term_fails(public_tree: Path) -> None:
    readme = public_tree / "README.md"
    term = "Co" + "dex"
    readme.write_text(readme.read_text(encoding="utf-8") + f"\n{term}\n", encoding="utf-8")
    assert any("internal workflow term" in error for error in validate_docs.validate(public_tree))


def test_invalid_json_fails(public_tree: Path) -> None:
    (public_tree / "configs" / "run.example.json").write_text("{", encoding="utf-8")
    assert any("invalid JSON" in error for error in validate_docs.validate(public_tree))


def test_floating_upstream_identity_fails(public_tree: Path) -> None:
    pins = _read_json(public_tree, "configs/upstream-pins.json")
    pins["lelab"]["commit"] = "main"
    _write_json(public_tree, "configs/upstream-pins.json", pins)
    assert any("lelab.commit" in error for error in validate_docs.validate(public_tree))


def test_example_cannot_enable_motion_or_upload(public_tree: Path) -> None:
    lab = _read_json(public_tree, "configs/lab.example.json")
    lab["motion"]["enabled"] = True
    lab["data"]["push_to_hub"] = True
    _write_json(public_tree, "configs/lab.example.json", lab)
    errors = validate_docs.validate(public_tree)
    assert any("motion must be disabled" in error for error in errors)
    assert any("push_to_hub must be false" in error for error in errors)


def test_example_cannot_claim_real_run(public_tree: Path) -> None:
    run = _read_json(public_tree, "configs/run.example.json")
    run["status"] = "PASS"
    run["observed_at"] = "2026-01-01T00:00:00Z"
    _write_json(public_tree, "configs/run.example.json", run)
    errors = validate_docs.validate(public_tree)
    assert any("status must remain NOT_RUN" in error for error in errors)
    assert any("cannot claim a real execution" in error for error in errors)


def test_duplicate_camera_mapping_fails(public_tree: Path) -> None:
    lab = _read_json(public_tree, "configs/lab.example.json")
    lab["cameras"]["wrist"]["opencv_index"] = 0
    lab["cameras"]["front"]["opencv_index"] = 0
    _write_json(public_tree, "configs/lab.example.json", lab)
    assert any("camera opencv_index values must differ" in error for error in validate_docs.validate(public_tree))


def test_invisible_unicode_fails(public_tree: Path) -> None:
    readme = public_tree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\u200b", encoding="utf-8")
    assert any("invisible Unicode" in error for error in validate_docs.validate(public_tree))
