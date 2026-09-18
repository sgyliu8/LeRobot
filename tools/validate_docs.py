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
    Path("templates/EXPERIMENT.md"),
    Path("templates/EVALUATION.md"),
)

JSON_FILES = (
    Path("configs/lab.example.json"),
    Path("configs/run.example.json"),
    Path("configs/upstream-pins.json"),
    Path("schemas/lab.schema.json"),
    Path("schemas/run.schema.json"),
)

REQUIRED_FILES = PUBLIC_MARKDOWN + JSON_FILES + (
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("scripts/lab.ps1"),
    Path("tools/audit_dataset.py"),
    Path("tools/bootstrap_upstream.ps1"),
    Path("tools/validate_docs.py"),
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


def _validate_tracked_surface(root: Path, tracked: tuple[Path, ...], errors: list[str]) -> None:
    tracked_set = set(tracked)
    expected_markdown = set(PUBLIC_MARKDOWN)
    tracked_markdown = {relative for relative in tracked_set if relative.suffix.casefold() == ".md"}

    for relative in sorted(expected_markdown - tracked_markdown):
        errors.append(f"public Markdown is not Git-tracked: {relative.as_posix()}")
    for relative in sorted(tracked_markdown - expected_markdown):
        errors.append(f"unexpected tracked Markdown: {relative.as_posix()}")

    encoded_terms = tuple(term.encode("utf-8") for term in PRIVATE_TERMS)
    for relative in sorted(tracked_set):
        path = root / relative
        try:
            content = path.read_bytes().lower()
        except OSError as exc:
            errors.append(f"{relative.as_posix()}: unable to inspect tracked content: {exc}")
            continue
        if any(term in content for term in encoded_terms):
            errors.append(f"{relative.as_posix()}: contains an internal workflow term")


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

    if isinstance(pins, dict):
        for component in ("lelab", "lerobot"):
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
