"""Prepare a local-only ROS 2 description package from the pinned UI assets."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import subprocess
from pathlib import Path

CMAKE = """cmake_minimum_required(VERSION 3.10.2)
project(so_arm_description)
find_package(ament_cmake REQUIRED)
install(DIRECTORY meshes urdf DESTINATION share/${PROJECT_NAME})
ament_package()
"""
LELAB_COMMIT = "6091a45811ef926a06b9b3622a9ab69fefb8bb7b"
LELAB_ORIGIN = "https://github.com/huggingface/leLab.git"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _source_provenance(source: Path, project_root: Path) -> dict[str, object]:
    default_source = (
        project_root / "_vendor/lelab/frontend/public/so-101-urdf"
    ).resolve()
    if source != default_source:
        return {"kind": "explicit_override", "verified_pin": False}

    repository = project_root / "_vendor/lelab"

    def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(repository), *args],
            check=check,
            capture_output=True,
            text=True,
        )

    origin = git("remote", "get-url", "origin").stdout.strip()
    head = git("rev-parse", "HEAD").stdout.strip()
    asset_changes = git(
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        "frontend/public/so-101-urdf",
    ).stdout.strip()
    if origin != LELAB_ORIGIN or head != LELAB_COMMIT or asset_changes:
        raise ValueError("Default ROS description assets are not from the clean pinned LeLab source")
    return {
        "kind": "pinned_lelab_vendor_assets",
        "verified_pin": True,
        "origin": origin,
        "commit": head,
    }


def prepare(
    source: Path,
    destination: Path,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, object]:
    project_root = project_root.resolve(strict=True)
    source = source.resolve(strict=True)
    destination = destination.resolve()
    local_root = (project_root / ".local").resolve()
    if destination != local_root and local_root not in destination.parents:
        raise ValueError("ROS description output must stay under the project .local directory")
    if destination.exists():
        raise FileExistsError(f"Refusing to replace existing ROS package: {destination}")
    required = [source / "package.xml", source / "urdf" / "so101_new_calib.urdf", source / "meshes"]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Description assets are incomplete: {missing}")

    provenance = _source_provenance(source, project_root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{secrets.token_hex(8)}.tmp")
    try:
        temporary.mkdir()
        shutil.copy2(source / "package.xml", temporary / "package.xml")
        shutil.copytree(source / "urdf", temporary / "urdf")
        shutil.copytree(source / "meshes", temporary / "meshes")
        (temporary / "CMakeLists.txt").write_text(CMAKE, encoding="utf-8")
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {
        "status": "PASS",
        "destination": str(destination),
        "urdf": str(destination / "urdf" / "so101_new_calib.urdf"),
        "mesh_files": len(list((destination / "meshes").glob("*.stl"))),
        "source_provenance": provenance,
        "boundary": "local build input only; no assets were added to Git",
    }


def main() -> int:
    root = PROJECT_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=root / "_vendor/lelab/frontend/public/so-101-urdf",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=root / ".local/ros2_ws/src/so_arm_description",
    )
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.destination), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
