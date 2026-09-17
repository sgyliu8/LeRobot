"""Offline regression tests. Uses temporary copies, never hardware or network."""
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pack_validator", ROOT / "tools/validate_pack.py")
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PackValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "pack"
        self.root.mkdir()
        # Copy only the documentation pack, never a future virtualenv/data tree.
        for relative in MODULE.REQUIRED:
            source = ROOT / relative
            if source.is_file():
                target = self.root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

    def rewrite_json(self, relative: str, update) -> None:
        path = self.root / relative
        value = json.loads(path.read_text(encoding="utf-8"))
        update(value)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def assert_error(self, text: str, *, strict: bool = False) -> None:
        self.assertTrue(any(text in error for error in MODULE.validate(self.root, strict)), text)

    def test_original_pack_passes(self) -> None:
        self.assertEqual(MODULE.validate(self.root), [])

    def test_missing_authority(self) -> None:
        (self.root / "docs/ROADMAP.md").unlink()
        self.assert_error("Missing required file: docs/ROADMAP.md")

    def test_wrong_repository(self) -> None:
        self.rewrite_json("configs/lab.example.json", lambda v: v["project"].update(repository="https://github.com/other/other.git"))
        self.assert_error("wrong project repository")

    def test_motion_enabled_is_rejected(self) -> None:
        self.rewrite_json("configs/lab.example.json", lambda v: v["motion"].update(enabled=True))
        self.assert_error("motion disabled")

    def test_external_upload_default_is_rejected(self) -> None:
        self.rewrite_json("configs/lab.example.json", lambda v: v["data"].update(push_to_hub=True))
        self.assert_error("disable external upload")

    def test_floating_upstream_commit_is_rejected(self) -> None:
        self.rewrite_json("configs/upstream-pins.json", lambda v: v["lelab"].update(commit="main"))
        self.assert_error("Invalid exact upstream commit")

    def test_duplicate_camera_identity_is_rejected(self) -> None:
        def update(v):
            for value in v["cameras"].values():
                value["device_identifier"] = "same-device"
        self.rewrite_json("configs/lab.example.json", update)
        self.assert_error("cannot share one device_identifier")

    def test_broken_link(self) -> None:
        with (self.root / "README.md").open("a", encoding="utf-8") as handle:
            handle.write("\n[broken](docs/DOES-NOT-EXIST.md)\n")
        self.assert_error("Broken local link")

    def test_unknown_source_reference(self) -> None:
        self.rewrite_json("configs/upstream-pins.json", lambda v: v["lelab"].update(source_ids=["S99"]))
        self.assert_error("unknown source ID")

    def test_malformed_json(self) -> None:
        (self.root / "configs/lab.example.json").write_text("{bad", encoding="utf-8")
        self.assert_error("JSON lab.example.json")

    def test_fake_runtime_result_is_rejected(self) -> None:
        self.rewrite_json("configs/run.example.json", lambda v: v.update(status="PASS", metrics={"success": 1}))
        self.assert_error("without invented metrics")

    def test_delivery_size_drift(self) -> None:
        with (self.root / "CHANGELOG.md").open("a", encoding="utf-8") as handle:
            handle.write("\nNew edit.\n")
        self.assert_error("Delivery file missing or size changed", strict=True)

    def test_regular_mode_allows_new_implementation_files(self) -> None:
        (self.root / "new_runtime_file.py").write_text("# New implementation\n", encoding="utf-8")
        self.assertEqual(MODULE.validate(self.root), [])

    def test_illustrative_code_is_not_a_link(self) -> None:
        with (self.root / "README.md").open("a", encoding="utf-8") as handle:
            handle.write("\n```markdown\n[example](not-an-actual-file.md)\n```\n")
        self.assertEqual(MODULE.validate(self.root), [])


if __name__ == "__main__":
    unittest.main()
