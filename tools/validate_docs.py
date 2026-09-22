#!/usr/bin/env python3
"""Validate the public documentation surface and safe example configuration."""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PUBLIC_MARKDOWN = (
    Path("README.md"),
    Path("docs/GETTING_STARTED.md"),
    Path("docs/HARDWARE.md"),
    Path("docs/DATA_WORKFLOW.md"),
    Path("docs/DATA_CONTRACTS.md"),
    Path("docs/SAFETY.md"),
    Path("docs/ARCHITECTURE.md"),
    Path("docs/DEVELOPMENT.md"),
    Path("docs/TROUBLESHOOTING.md"),
    Path("docs/PROJECT_STATUS.md"),
    Path("docs/TASK_COLOR_SORTING.md"),
    Path("docs/POLICIES.md"),
    Path("examples/mujoco/README.md"),
    Path("integrations/ros2/README.md"),
    Path("experiments/vision_geometry/README.md"),
    Path("templates/EXPERIMENT.md"),
    Path("templates/EVALUATION.md"),
)

JSON_FILES = (
    Path("configs/lab.example.json"),
    Path("configs/run.example.json"),
    Path("configs/upstream-pins.json"),
    Path("schemas/lab.schema.json"),
    Path("schemas/run.schema.json"),
    Path("experiments/vision_geometry/config.example.json"),
    Path("configs/tasks/color_sorting.example.json"),
)

REQUIRED_FILES = PUBLIC_MARKDOWN + JSON_FILES + (
    Path("docs/assets/lab-overview.svg"),
    Path("Start-SO101-Lab.cmd"),
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("scripts/lab.ps1"),
    Path("scripts/workbench.ps1"),
    Path("scripts/maintenance.ps1"),
    Path("tools/runtime_check.py"),
    Path("tools/audit_dataset.py"),
    Path("tools/bootstrap_upstream.ps1"),
    Path("tools/validate_docs.py"),
    Path("so101_lab/__init__.py"),
    Path("so101_lab/color_sorting.py"),
    Path("so101_lab/color_sorting_cli.py"),
    Path("so101_lab/training_split.py"),
    Path("examples/mujoco/bootstrap_model.ps1"),
    Path("examples/mujoco/pyproject.toml"),
    Path("examples/mujoco/replay_episode.py"),
    Path("examples/mujoco/test_replay_episode.py"),
    Path("examples/mujoco/uv.lock"),
    Path("integrations/ros2/joint_state_replay.py"),
    Path("integrations/ros2/prepare_description.py"),
    Path("integrations/ros2/so101.rviz"),
)

MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
WINDOWS_ABSOLUTE_PATH = re.compile(r"(?<![\w])(?:[A-Za-z]:[\\/])")
URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
HEX_COMMIT = re.compile(r"^[0-9a-f]{40}$")
INVISIBLE = {"\ufeff", "\u200b", "\u200c", "\u200d", "\u2060"}
PRIVATE_TERMS = (
    "co" + "dex",
    "golden " + "context",
    "context " + "pack",
    "sub" + "agent",
)
PERSONAL_HOME = re.compile(rb"[a-z]:[\\/]+users[\\/]+[a-z0-9._-]+[\\/]", re.IGNORECASE)
INTERNAL_PATHS = (
    b".local/" + b"planning/",
    b".local\\" + b"planning\\",
    b".local/" + b"internal-docs/",
)
DATED_LOCAL_DATASET = re.compile(rb"\blocal/[a-z0-9._-]+_\d{8}_\d{6}\b", re.IGNORECASE)
LOCAL_PUBLICATION_DENYLIST = Path(".local/publication-denylist.txt")
PRIVATE_ARTIFACT_SUFFIXES = {
    ".avi",
    ".bag",
    ".ckpt",
    ".db3",
    ".jsonl",
    ".log",
    ".mkv",
    ".mov",
    ".mp4",
    ".parquet",
    ".pt",
    ".pth",
    ".safetensors",
    ".sqlite",
    ".sqlite3",
}


def _tracked_files(
    root: Path,
    errors: list[str],
    supplied: Iterable[Path | str] | None,
) -> tuple[Path, ...]:
    if supplied is not None:
        candidates = tuple(Path(value) for value in supplied)
    else:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "ls-files", "-z", "--cached"],
                check=False,
                capture_output=True,
            )
        except OSError as exc:
            errors.append(f"unable to enumerate Git-tracked files: {exc}")
            return ()
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            errors.append(f"unable to enumerate Git-tracked files: {detail or 'git failed'}")
            return ()
        candidates = tuple(Path(value.decode("utf-8")) for value in result.stdout.split(b"\0") if value)

    normalized: list[Path] = []
    for relative in candidates:
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"tracked path escapes repository: {relative.as_posix()}")
            continue
        normalized.append(Path(relative.as_posix()))
    return tuple(normalized)


def _local_private_terms(root: Path, errors: list[str]) -> tuple[bytes, ...]:
    path = root / LOCAL_PUBLICATION_DENYLIST
    if not path.exists():
        return ()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        errors.append(f"unable to read local publication denylist: {exc}")
        return ()

    terms: list[bytes] = []
    for line_number, line in enumerate(lines, start=1):
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        if len(value) < 4:
            errors.append(f"local publication denylist line {line_number} is too short")
            continue
        terms.append(value.casefold().encode("utf-8"))
    return tuple(terms)


def _validate_tracked_surface(root: Path, tracked: tuple[Path, ...], errors: list[str]) -> None:
    tracked_set = set(tracked)
    expected_markdown = set(PUBLIC_MARKDOWN)
    tracked_markdown = {relative for relative in tracked_set if relative.suffix.casefold() == ".md"}

    for relative in sorted(expected_markdown - tracked_markdown):
        errors.append(f"public Markdown is not Git-tracked: {relative.as_posix()}")
    for relative in sorted(tracked_markdown - expected_markdown):
        errors.append(f"unexpected tracked Markdown: {relative.as_posix()}")

    encoded_terms = tuple(term.encode("utf-8") for term in PRIVATE_TERMS)
    local_private_terms = _local_private_terms(root, errors)
    for relative in sorted(tracked_set):
        if relative.suffix.casefold() in PRIVATE_ARTIFACT_SUFFIXES:
            errors.append(f"{relative.as_posix()}: private runtime artifact must not be Git-tracked")
        path = root / relative
        try:
            content = path.read_bytes().lower()
        except OSError as exc:
            errors.append(f"{relative.as_posix()}: unable to inspect tracked content: {exc}")
            continue
        if any(term in content for term in encoded_terms):
            errors.append(f"{relative.as_posix()}: contains an internal workflow term")
        if PERSONAL_HOME.search(content):
            errors.append(f"{relative.as_posix()}: contains a personal home path")
        if any(fragment in content for fragment in INTERNAL_PATHS):
            errors.append(f"{relative.as_posix()}: contains an internal local path")
        if DATED_LOCAL_DATASET.search(content):
            errors.append(f"{relative.as_posix()}: contains a dated local dataset identifier")
        if any(identifier in content for identifier in local_private_terms):
            errors.append(f"{relative.as_posix()}: contains a private lab identifier")


def _load_json(root: Path, relative: Path, errors: list[str]) -> object | None:
    path = root / relative
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{relative.as_posix()}: invalid JSON: {exc}")
        return None


def _validate_markdown(root: Path, errors: list[str]) -> None:
    for relative in PUBLIC_MARKDOWN:
        path = root / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{relative.as_posix()}: unreadable UTF-8: {exc}")
            continue

        if not text.strip():
            errors.append(f"{relative.as_posix()}: empty document")
        if any(character in text for character in INVISIBLE):
            errors.append(f"{relative.as_posix()}: contains invisible Unicode")
        if WINDOWS_ABSOLUTE_PATH.search(text):
            errors.append(f"{relative.as_posix()}: contains a Windows absolute path")

        lowered = text.casefold()
        for term in PRIVATE_TERMS:
            if term in lowered:
                errors.append(f"{relative.as_posix()}: contains an internal workflow term")

        for match in MARKDOWN_LINK.finditer(text):
            target = match.group(1).strip().strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:", "//")):
                continue
            if URI_SCHEME.match(target):
                errors.append(f"{relative.as_posix()}: unsupported link scheme: {target}")
                continue
            target = target.split("#", 1)[0].split("?", 1)[0]
            if not target:
                continue
            candidate = Path(target)
            if candidate.is_absolute() or candidate.drive or target.startswith(("/", "\\")):
                errors.append(f"{relative.as_posix()}: link escapes repository: {target}")
                continue
            from_root = path.parent.relative_to(root) / candidate
            normalized = Path(os.path.normpath(from_root))
            if normalized.is_absolute() or normalized.drive or ".." in normalized.parts:
                errors.append(f"{relative.as_posix()}: link escapes repository: {target}")
                continue
            resolved = root / normalized
            cursor = root
            symlinked = False
            for part in normalized.parts:
                cursor /= part
                if cursor.is_symlink() or cursor.is_junction():
                    errors.append(f"{relative.as_posix()}: link traverses a linked path: {target}")
                    symlinked = True
                    break
            if not symlinked and not resolved.exists():
                errors.append(f"{relative.as_posix()}: broken relative link: {target}")


def _validate_examples(root: Path, errors: list[str]) -> None:
    lab = _load_json(root, Path("configs/lab.example.json"), errors)
    run = _load_json(root, Path("configs/run.example.json"), errors)
    pins = _load_json(root, Path("configs/upstream-pins.json"), errors)
    _load_json(root, Path("schemas/lab.schema.json"), errors)
    _load_json(root, Path("schemas/run.schema.json"), errors)
    color_sorting = _load_json(root, Path("configs/tasks/color_sorting.example.json"), errors)

    if isinstance(pins, dict):
        for component in ("lelab", "lerobot", "mujoco_menagerie"):
            commit = pins.get(component, {}).get("commit")
            if not isinstance(commit, str) or not HEX_COMMIT.fullmatch(commit):
                errors.append(f"configs/upstream-pins.json: {component}.commit is not a full commit")
        if pins.get("python", {}).get("minor") != "3.12":
            errors.append("configs/upstream-pins.json: Python minor must remain 3.12")
        patch_set = pins.get("patch_set")
        if not isinstance(patch_set, list) or len(patch_set) != 1 or not isinstance(patch_set[0], str):
            errors.append("configs/upstream-pins.json: patch_set must contain exactly one path")
        else:
            patch_relative = Path(patch_set[0])
            if (
                patch_relative.is_absolute()
                or ".." in patch_relative.parts
                or patch_relative.suffix.casefold() != ".patch"
            ):
                errors.append("configs/upstream-pins.json: patch_set path is unsafe or not a patch")
            elif not (root / patch_relative).is_file():
                errors.append(f"configs/upstream-pins.json: patch is missing: {patch_relative.as_posix()}")

    if isinstance(lab, dict):
        if lab.get("server", {}).get("host") not in {"127.0.0.1", "localhost"}:
            errors.append("configs/lab.example.json: server must bind loopback")
        if lab.get("motion", {}).get("enabled") is not False:
            errors.append("configs/lab.example.json: example motion must be disabled")
        data = lab.get("data", {})
        for key in ("push_to_hub", "wandb_enabled", "cloud_training_enabled"):
            if data.get(key) is not False:
                errors.append(f"configs/lab.example.json: {key} must be false")
        devices = lab.get("devices", {})
        leader = devices.get("leader", {})
        follower = devices.get("follower", {})
        if leader.get("port") is not None or follower.get("port") is not None:
            errors.append("configs/lab.example.json: example serial ports must be null")
        if leader.get("id") == follower.get("id"):
            errors.append("configs/lab.example.json: leader and follower IDs must differ")
        cameras = lab.get("cameras", {})
        wrist = cameras.get("wrist", {})
        front = cameras.get("front", {})
        for key in ("device_identifier", "opencv_index"):
            value = wrist.get(key)
            if value is not None and value == front.get(key):
                errors.append(f"configs/lab.example.json: camera {key} values must differ")

    if isinstance(run, dict):
        if run.get("status") != "NOT_RUN":
            errors.append("configs/run.example.json: example status must remain NOT_RUN")
        if run.get("observed_at") is not None or run.get("project_commit") is not None:
            errors.append("configs/run.example.json: template cannot claim a real execution")

    if isinstance(color_sorting, dict):
        dataset = color_sorting.get("dataset", {})
        entities = color_sorting.get("entities", {})
        scene = color_sorting.get("scene", {})
        policy = color_sorting.get("policy", {})
        if color_sorting.get("task_id") != "color_sorting_v1" or color_sorting.get("stage") != "C0":
            errors.append("configs/tasks/color_sorting.example.json: public example must remain unexecuted C0")
        if dataset.get("repo_id") is not None:
            errors.append("configs/tasks/color_sorting.example.json: Dataset ID must remain unknown")
        if dataset.get("camera_aliases") != {"arm": "wrist", "table_veiw": "front"}:
            errors.append("configs/tasks/color_sorting.example.json: camera aliases are invalid")
        for key in ("hue_augmentation", "grayscale_augmentation", "color_changing_augmentation"):
            if dataset.get(key) is not False:
                errors.append(f"configs/tasks/color_sorting.example.json: {key} must remain false")
        colors = entities.get("colors", [])
        if len(colors) != 3 or any(not isinstance(item, dict) for item in colors) or any(
            item.get("display_name") is not None
            or item.get("hsv_ranges") != []
            or item.get("instance_ids") != []
            for item in colors
            if isinstance(item, dict)
        ):
            errors.append("configs/tasks/color_sorting.example.json: actual colors must remain unknown")
        if entities.get("cube_size_mm") is not None or any(
            item.get("opening_size_mm") is not None
            for item in entities.get("bins", [])
            if isinstance(item, dict)
        ):
            errors.append("configs/tasks/color_sorting.example.json: physical dimensions must remain unknown")
        if scene.get("source_roi") is not None or any(
            item.get("interior_roi") is not None or item.get("rim_roi") is not None
            for item in scene.get("bin_regions", [])
            if isinstance(item, dict)
        ):
            errors.append("configs/tasks/color_sorting.example.json: physical ROIs must remain unknown")
        if (
            scene.get("layout_id") is not None
            or scene.get("observer_camera_key") != "table_veiw"
            or scene.get("gripper_exclusion_rois") != []
        ):
            errors.append("configs/tasks/color_sorting.example.json: layout and exclusion ROIs must remain unknown")
        if any(
            color_sorting.get(key) is not None
            for key in ("recording_profile_id", "calibration_id", "project_commit")
        ):
            errors.append("configs/tasks/color_sorting.example.json: execution identities must remain unknown")
        if (
            policy.get("type") != "act"
            or policy.get("chunk_size") != 32
            or policy.get("n_action_steps") != 8
            or policy.get("task_text_consumed") is not False
        ):
            errors.append("configs/tasks/color_sorting.example.json: ACT candidate contract is invalid")


def validate(
    root: Path = ROOT,
    *,
    tracked_files: Iterable[Path | str] | None = None,
) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    tracked = _tracked_files(root, errors, tracked_files)
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append(f"missing required file: {relative.as_posix()}")

    if errors:
        return errors

    _validate_tracked_surface(root, tracked, errors)
    _validate_markdown(root, errors)
    _validate_examples(root, errors)
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("DOCS_STATIC_PASS - public documentation and examples only; no hardware validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
