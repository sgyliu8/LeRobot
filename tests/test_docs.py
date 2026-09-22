from __future__ import annotations

import importlib.util
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("validate_docs", ROOT / "tools" / "validate_docs.py")
assert SPEC and SPEC.loader
validate_docs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate_docs)


@pytest.fixture()
def public_tree(tmp_path: Path) -> Path:
    pins = json.loads((ROOT / "configs" / "upstream-pins.json").read_text(encoding="utf-8"))
    required = (*validate_docs.REQUIRED_FILES, *(Path(value) for value in pins["patch_set"]))
    for relative in required:
        source = ROOT / relative
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return tmp_path


def _read_json(root: Path, relative: str) -> dict:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def _write_json(root: Path, relative: str, value: dict) -> None:
    (root / relative).write_text(json.dumps(value), encoding="utf-8")


def _validate(root: Path) -> list[str]:
    tracked = [
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and ".local" not in path.relative_to(root).parts
    ]
    return validate_docs.validate(root, tracked_files=tracked)


def test_public_tree_passes(public_tree: Path) -> None:
    assert _validate(public_tree) == []


def test_missing_required_document_fails(public_tree: Path) -> None:
    (public_tree / "docs" / "SAFETY.md").unlink()
    assert any("missing required file" in error for error in _validate(public_tree))


def test_missing_readme_illustration_fails(public_tree: Path) -> None:
    (public_tree / "docs/assets/lab-overview.svg").unlink()
    assert any("missing required file" in error for error in _validate(public_tree))


def test_readme_illustration_is_accessible_and_self_contained(public_tree: Path) -> None:
    svg = ET.parse(public_tree / "docs/assets/lab-overview.svg").getroot()
    namespace = "{http://www.w3.org/2000/svg}"
    assert svg.tag == f"{namespace}svg"
    assert svg.attrib["viewBox"] == "0 0 1200 660"
    for tag in ("title", "desc"):
        element = svg.find(f"{namespace}{tag}")
        assert element is not None and element.text
        assert element.attrib["id"] in svg.attrib["aria-labelledby"].split()
    for element in svg.iter():
        assert element.tag not in {f"{namespace}script", f"{namespace}foreignObject", f"{namespace}image"}
        assert not any(key.lower().startswith("on") or key.endswith("href") for key in element.attrib)


def test_broken_relative_link_fails(public_tree: Path) -> None:
    readme = public_tree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\n[missing](docs/NOPE.md)\n", encoding="utf-8")
    assert any("broken relative link" in error for error in _validate(public_tree))


def test_protocol_relative_link_never_reaches_windows_path_resolution(
    public_tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    readme = public_tree / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\n[external](//example.invalid/share)\n",
        encoding="utf-8",
    )
    original_resolve = Path.resolve

    def guarded_resolve(path: Path, *args, **kwargs):
        if str(path).startswith(("//", "\\\\")):
            raise AssertionError("network path resolution attempted")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", guarded_resolve)
    assert _validate(public_tree) == []


def test_windows_unc_link_is_rejected_without_resolution(public_tree: Path) -> None:
    readme = public_tree / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\n[private](\\\\server\\share)\n",
        encoding="utf-8",
    )
    errors = _validate(public_tree)
    assert any("link escapes repository" in error for error in errors)


def test_absolute_windows_path_fails(public_tree: Path) -> None:
    readme = public_tree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\nC:\\private\\file\n", encoding="utf-8")
    assert any("Windows absolute path" in error for error in _validate(public_tree))


def test_internal_workflow_term_fails(public_tree: Path) -> None:
    readme = public_tree / "README.md"
    term = "Co" + "dex"
    readme.write_text(readme.read_text(encoding="utf-8") + f"\n{term}\n", encoding="utf-8")
    assert any("internal workflow term" in error for error in _validate(public_tree))


def test_invalid_json_fails(public_tree: Path) -> None:
    (public_tree / "configs" / "run.example.json").write_text("{", encoding="utf-8")
    assert any("invalid JSON" in error for error in _validate(public_tree))


def test_floating_upstream_identity_fails(public_tree: Path) -> None:
    pins = _read_json(public_tree, "configs/upstream-pins.json")
    pins["lelab"]["commit"] = "main"
    _write_json(public_tree, "configs/upstream-pins.json", pins)
    assert any("lelab.commit" in error for error in _validate(public_tree))


def test_example_cannot_enable_motion_or_upload(public_tree: Path) -> None:
    lab = _read_json(public_tree, "configs/lab.example.json")
    lab["motion"]["enabled"] = True
    lab["data"]["push_to_hub"] = True
    _write_json(public_tree, "configs/lab.example.json", lab)
    errors = _validate(public_tree)
    assert any("motion must be disabled" in error for error in errors)
    assert any("push_to_hub must be false" in error for error in errors)


def test_example_cannot_claim_real_run(public_tree: Path) -> None:
    run = _read_json(public_tree, "configs/run.example.json")
    run["status"] = "PASS"
    run["observed_at"] = "2026-01-01T00:00:00Z"
    _write_json(public_tree, "configs/run.example.json", run)
    errors = _validate(public_tree)
    assert any("status must remain NOT_RUN" in error for error in errors)
    assert any("cannot claim a real execution" in error for error in errors)


def test_duplicate_camera_mapping_fails(public_tree: Path) -> None:
    lab = _read_json(public_tree, "configs/lab.example.json")
    lab["cameras"]["wrist"]["opencv_index"] = 0
    lab["cameras"]["front"]["opencv_index"] = 0
    _write_json(public_tree, "configs/lab.example.json", lab)
    assert any("camera opencv_index values must differ" in error for error in _validate(public_tree))


def test_invisible_unicode_fails(public_tree: Path) -> None:
    readme = public_tree / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\u200b", encoding="utf-8")
    assert any("invisible Unicode" in error for error in _validate(public_tree))


def test_unexpected_tracked_markdown_fails(public_tree: Path) -> None:
    (public_tree / "INTERNAL.md").write_text("private notes\n", encoding="utf-8")
    assert any("unexpected tracked Markdown" in error for error in _validate(public_tree))


def test_internal_term_in_non_markdown_tracked_file_fails(public_tree: Path) -> None:
    term = "Co" + "dex"
    (public_tree / "internal.txt").write_text(term, encoding="utf-8")
    assert any("internal workflow term" in error for error in _validate(public_tree))


def test_local_publication_denylist_rejects_matching_tracked_content(public_tree: Path) -> None:
    denylist = public_tree / ".local" / "publication-denylist.txt"
    denylist.parent.mkdir(parents=True)
    denylist.write_text("PRIVATE-PORT-FIXTURE\n", encoding="utf-8")
    (public_tree / "device.txt").write_text("PRIVATE-PORT-FIXTURE", encoding="utf-8")
    assert any("private lab identifier" in error for error in _validate(public_tree))


def test_dated_local_dataset_identifier_in_tracked_file_fails(public_tree: Path) -> None:
    synthetic_identifier = "local/fixture_" + "20300102" + "_" + "030405"
    (public_tree / "dataset.txt").write_text(synthetic_identifier, encoding="utf-8")
    assert any("dated local dataset identifier" in error for error in _validate(public_tree))


def test_private_runtime_artifact_suffix_fails(public_tree: Path) -> None:
    (public_tree / "training.jsonl").write_text("{}\n", encoding="utf-8")
    assert any("private runtime artifact" in error for error in _validate(public_tree))


def test_bootstrap_reads_the_authoritative_pin_manifest(public_tree: Path) -> None:
    pins = _read_json(public_tree, "configs/upstream-pins.json")
    script = (public_tree / "tools" / "bootstrap_upstream.ps1").read_text(encoding="utf-8")
    assert "upstream-pins.json" in script
    assert pins["lelab"]["commit"] not in script
    assert pins["lelab"]["repository"] not in script
    assert "hash-object" in script
    assert "frontend/dist" in script
    assert "Assert-NoReparseTree -RootPath $vendorRoot" in script
    assert "must use a local .git directory" in script
    assert "LeLab node_modules" in script
