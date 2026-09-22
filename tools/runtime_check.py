"""Local installation identity; never imports jobs/server or opens a device."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_local_path(root: Path, path: Path) -> None:
    relative = path.absolute().relative_to(root.absolute())
    cursor = root
    for part in (None, *relative.parts):
        if part is not None:
            cursor /= part
        if cursor.is_symlink() or cursor.is_junction():
            raise ValueError(f"installation path crosses a linked directory: {cursor.name}")


def code_identity(root: Path) -> dict:
    pins = json.loads((root / "configs/upstream-pins.json").read_text(encoding="utf-8"))
    source = root / "_vendor/lelab"
    assert_local_path(root, source)
    paths = sorted(
        list((source / "lelab").rglob("*.py"))
        + [p for p in (source / "frontend/dist").rglob("*") if p.is_file()]
    )
    digest = hashlib.sha256()
    for path in paths:
        assert_local_path(root, path)
        digest.update(path.relative_to(source).as_posix().encode())
        digest.update(path.read_bytes())
    for path in sorted((root / "so101_lab").glob("*.py")):
        assert_local_path(root, path)
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    commit = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    return {
        "project_commit": commit,
        "patch_sha256": file_hash(root / pins["patch_set"][0]),
        "lock_sha256": file_hash(root / "uv.lock"),
        "source_sha256": digest.hexdigest(),
        "lelab_commit": pins["lelab"]["commit"],
        "lerobot_commit": pins["lerobot"]["commit"],
    }


def check_environment(root: Path) -> list[str]:
    errors = []
    if sys.version_info[:2] != (3, 12):
        errors.append("Python 3.12 is required")
    if Path(sys.prefix).resolve() != (root / ".venv").resolve():
        errors.append("Python environment belongs to another folder; run Setup here")
    for name, expected in (("lelab", root / "_vendor/lelab/lelab"),):
        spec = importlib.util.find_spec(name)
        if spec is None or spec.origin is None or Path(spec.origin).resolve().parent != expected.resolve():
            errors.append(f"{name} import does not belong to this checkout; run Setup")
    try:
        dist = importlib.metadata.distribution("lerobot")
        direct = json.loads(dist.read_text("direct_url.json") or "{}")
        pins = json.loads((root / "configs/upstream-pins.json").read_text(encoding="utf-8"))
        if direct.get("vcs_info", {}).get("commit_id") != pins["lerobot"]["commit"]:
            errors.append("LeRobot resolved commit does not match the pinned version")
        if not Path(dist.locate_file("")).resolve().is_relative_to((root / ".venv").resolve()):
            errors.append("LeRobot is imported from outside this environment")
    except importlib.metadata.PackageNotFoundError:
        errors.append("LeRobot is not installed")
    if not (root / "_vendor/lelab/frontend/dist/index.html").is_file():
        errors.append("Built LeLab UI is missing; run Setup")
    spec = importlib.util.find_spec("so101_lab")
    if spec is None or spec.origin is None or Path(spec.origin).resolve().parent != (root / "so101_lab").resolve():
        errors.append("project package is not installed from this checkout; run Setup")
    return errors


def active_project_processes(root: Path) -> list[int]:
    import psutil

    matches = []
    current = psutil.Process()
    ancestors = {p.pid for p in current.parents()} | {current.pid}
    for process in psutil.process_iter(["pid", "name"]):
        if process.pid in ancestors or "python" not in (process.info["name"] or "").lower():
            continue
        try:
            if Path(process.cwd()).resolve() == root.resolve():
                matches.append(process.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", action="store_true", help="record successful explicit Setup")
    parser.add_argument("--maintenance", action="store_true", help="refuse changes while project Python runs")
    parser.add_argument("--compute", action="store_true", help="also inspect available PyTorch devices")
    args = parser.parse_args()
    if args.maintenance:
        active = active_project_processes(ROOT)
        print(json.dumps({"active_project_pids": active}))
        return 2 if active else 0
    errors = check_environment(ROOT)
    if errors:
        print(json.dumps({"ready": False, "issues": errors}, indent=2))
        return 2
    identity = code_identity(ROOT)
    receipt = ROOT / ".local/runtime/install.json"
    assert_local_path(ROOT, receipt)
    if args.record:
        receipt.parent.mkdir(parents=True, exist_ok=True)
        temporary = receipt.with_suffix(".tmp")
        assert_local_path(ROOT, temporary)
        temporary.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, receipt)
    else:
        try:
            installed = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            installed = {}
        for key in ("patch_sha256", "lock_sha256", "source_sha256"):
            if installed.get(key) != identity[key]:
                errors.append(f"installation differs at {key}; run Setup while the workbench is stopped")
    result = {"ready": not errors, "issues": errors, "identity": identity}
    if args.compute:
        import torch

        result["compute"] = {
            "torch": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_build": torch.version.cuda,
            "mps_available": bool(hasattr(torch.backends, "mps") and torch.backends.mps.is_available()),
            "xpu_available": bool(hasattr(torch, "xpu") and torch.xpu.is_available()),
        }
    print(json.dumps(result, indent=2))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
