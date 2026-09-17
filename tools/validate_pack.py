#!/usr/bin/env python3
"""Read-only, standard-library checks for the SO101 context pack.

This validates the delivered documents and examples, not LeLab, devices, safety,
full JSON Schema compliance, or operational permission. No network or subprocess.
Use --strict only to compare an untouched delivery with PACK_MANIFEST.json.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

ROOT_MARKDOWN = {"README.md", "AGENTS.md", "HANDOFF.md", "CHANGELOG.md"}
REQUIRED = ROOT_MARKDOWN | {
    "docs/REQUIREMENTS.md", "docs/ARCHITECTURE.md", "docs/ROADMAP.md",
    "docs/UI_SPEC.md", "docs/DATA_CONTRACTS.md", "docs/SECURITY.md",
    "docs/DEPENDENCIES.md", "docs/TEST_PLAN.md", "docs/CI_POLICY.md",
    "docs/architecture/ADR-001-BOUNDARIES.md", "docs/architecture/ADR-002-PATCHES.md",
    "docs/operations/BOOTSTRAP.md", "docs/operations/HARDWARE_BRINGUP.md",
    "docs/operations/COMPUTER_USE_DEBUGGING.md",
    "docs/operations/DATA_TRAIN_EVALUATE.md", "docs/operations/TROUBLESHOOTING.md",
    "docs/research/SOURCES.json", "docs/research/SOURCE_AUDIT.md",
    "docs/reviews/REVIEW_PROTOCOL.md", "docs/reviews/THREE_ROUND_REVIEW.md",
    "docs/reviews/PACK_VALIDATION.md", "docs/prompts/CODEX_START.md",
    "docs/prompts/CODEX_RESUME.md", "configs/upstream-pins.json",
    "configs/lab.example.json", "configs/run.example.json",
    "schemas/lab.schema.json", "schemas/run.schema.json",
    "templates/EXPERIMENT.md", "templates/EVALUATION.md",
    ".gitignore", ".gitattributes", ".editorconfig", "PACK_MANIFEST.json",
    "tools/validate_pack.py", "tests/test_validate_pack.py",
}
PROJECT_REPO = "https://github.com/sgyliu8/LeRobot.git"


def _read_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("top level must be an object")
        return value
    except (OSError, UnicodeError, ValueError) as exc:
        errors.append(f"JSON {path.name}: {exc}")
        return {}


def _prose_only(text: str) -> str:
    """Remove fenced code so illustrative paths/Markdown are not link-checked."""
    return re.sub(r"(?ms)^\s*(`{3,}|~{3,})[^\n]*\n.*?^\s*\1\s*$", "", text)


def validate(root: Path, strict: bool = False) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    if not root.is_dir():
        return [f"Pack root does not exist: {root}"]
    for relative in sorted(REQUIRED):
        if not (root / relative).is_file():
            errors.append(f"Missing required file: {relative}")
    root_md = {p.name for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".md"}
    if root_md != ROOT_MARKDOWN:
        errors.append("Root must have exactly README/AGENTS/HANDOFF/CHANGELOG.md")
    agents = root / "AGENTS.md"
    if agents.is_file() and agents.stat().st_size > 32768:
        errors.append("AGENTS.md exceeds 32 KiB; reduce required agent context")

    # Deliberately exclude virtualenv/vendor/private trees from future checks.
    docs = [root / name for name in ROOT_MARKDOWN]
    for folder in ("docs", "templates"):
        docs += list((root / folder).rglob("*.md")) if (root / folder).is_dir() else []
    prose: dict[Path, str] = {}
    for path in docs:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"Unreadable text {path.relative_to(root)}: {exc}")
            continue
        if not text.strip():
            errors.append(f"Empty document: {path.relative_to(root)}")
        if "\u200b" in text or "\x00" in text:
            errors.append(f"Invisible control/zero-width character: {path.relative_to(root)}")
        prose[path] = _prose_only(text)
        for target in re.findall(r"\[[^\]\n]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)", prose[path]):
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith(("#", "//")):
                continue
            resolved = (path.parent / unquote(parsed.path)).resolve()
            if not resolved.is_relative_to(root):
                errors.append(f"Link leaves pack: {path.relative_to(root)} -> {target}")
            elif not resolved.exists():
                errors.append(f"Broken local link: {path.relative_to(root)} -> {target}")

    objects: dict[str, dict[str, Any]] = {}
    json_paths = [root / "PACK_MANIFEST.json", root / "docs/research/SOURCES.json"]
    for folder in ("configs", "schemas"):
        if (root / folder).is_dir():
            json_paths += list((root / folder).glob("*.json"))
    for path in json_paths:
        if path.is_file():
            objects[path.relative_to(root).as_posix()] = _read_json(path, errors)

    sources = objects.get("docs/research/SOURCES.json", {}).get("sources", [])
    if not isinstance(sources, list):
        errors.append("sources must be an array")
        sources = []
    ids = [s.get("id") for s in sources if isinstance(s, dict)]
    if not ids or len(ids) != len(sources) or len(ids) != len(set(str(x) for x in ids)):
        errors.append("Source IDs are missing, malformed or duplicated")
    known = {i for i in ids if isinstance(i, str)}
    for s in sources:
        if not isinstance(s, dict):
            continue
        if not all(s.get(k) for k in ("id", "title", "url", "reading_depth", "observed_on")):
            errors.append(f"Incomplete source record: {s.get('id')}")
    for path, text in prose.items():
        for ref in sorted(set(re.findall(r"\bS\d{2}\b", text)) - known):
            errors.append(f"Unknown source ID {ref} in {path.relative_to(root)}")

    pins = objects.get("configs/upstream-pins.json", {})
    for name in ("lelab", "lerobot"):
        item = pins.get(name, {})
        if not isinstance(item, dict) or not re.fullmatch(r"[0-9a-f]{40}", str(item.get("commit", ""))):
            errors.append(f"Invalid exact upstream commit: {name}")
            continue
        for source_id in item.get("source_ids", []):
            if source_id not in known:
                errors.append(f"Upstream {name} references unknown source ID: {source_id}")
    if pins.get("python", {}).get("minor") != "3.12":
        errors.append("Candidate Python minor must be 3.12")

    # These are checks on SAFE TEMPLATES, not authorization for live configs.
    lab = objects.get("configs/lab.example.json", {})
    if lab.get("project", {}).get("repository") != PROJECT_REPO:
        errors.append("Example has wrong project repository")
    if lab.get("config_kind") != "project_example_not_lelab_api":
        errors.append("Example must distinguish project config from upstream API")
    if lab.get("server", {}).get("host") != "127.0.0.1":
        errors.append("Example server must bind to loopback")
    motion = lab.get("motion", {})
    if motion.get("enabled") is not False or motion.get("bench_session") != "not_confirmed":
        errors.append("Example must have motion disabled and session unconfirmed")
    data = lab.get("data", {})
    if any(data.get(k) is not False for k in ("push_to_hub", "wandb_enabled", "cloud_training_enabled")):
        errors.append("Example must disable external upload/logging/cloud execution")
    devices = lab.get("devices", {})
    for side in ("leader", "follower"):
        item = devices.get(side, {})
        if item.get("port") is not None or item.get("identity_verified") is not False:
            errors.append(f"Example cannot pretend a verified port: {side}")
    cameras = lab.get("cameras", {})
    if set(cameras) != {"wrist", "front"}:
        errors.append("Camera roles must be wrist and front")
    populated = [c.get("device_identifier") for c in cameras.values() if isinstance(c, dict) and c.get("device_identifier") is not None]
    if len(populated) != len(set(str(i) for i in populated)):
        errors.append("Distinct camera roles cannot share one device_identifier")
    run = objects.get("configs/run.example.json", {})
    if run.get("status") != "NOT_RUN" or run.get("metrics") != {} or run.get("evidence") != []:
        errors.append("Run example must remain NOT_RUN, without invented metrics or evidence")

    if strict:
        manifest = objects.get("PACK_MANIFEST.json", {})
        files = manifest.get("files", [])
        if not files or not isinstance(files, list):
            errors.append("Strict validation needs a populated delivery manifest")
        else:
            for entry in files:
                if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                    errors.append("Malformed manifest entry")
                    continue
                path = (root / entry["path"]).resolve()
                if not path.is_relative_to(root):
                    errors.append("Manifest path leaves pack")
                elif not path.is_file() or path.stat().st_size != entry.get("bytes"):
                    errors.append(f"Delivery file missing or size changed: {entry['path']}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--strict", action="store_true", help="check initial delivery file sizes, not for edited repos")
    args = parser.parse_args()
    errors = validate(args.root, args.strict)
    if errors:
        print("PACK_STATIC_FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PACK_STATIC_PASS — documents/examples only; no runtime, hardware or safety validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
