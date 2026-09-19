from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _load_ros_module():
    module_path = ROOT / "integrations/ros2/joint_state_replay.py"
    name = "so101_joint_state_replay_test"
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def _load_prepare_module():
    module_path = ROOT / "integrations/ros2/prepare_description.py"
    name = "so101_prepare_description_test"
    spec = importlib.util.spec_from_file_location(name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _trajectory_row(
    module,
    timestamp: float,
    *,
    frame_index: int = 0,
    expected_frames: int = 1,
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "dataset_id": "local/example",
        "episode": 0,
        "frame_index": frame_index,
        "expected_frames": expected_frames,
        "source_episode_arrays_sha256": "a" * 64,
        "timestamp": timestamp,
        "source_feature_names": list(module.SOURCE_FEATURE_NAMES),
        "source_units": list(module.SOURCE_UNITS),
        "model_joint_names": list(module.MODEL_NAMES),
        "positions_rad": [0.0] * 6,
        "transform": {"kind": "dataset_state_to_model_radians"},
    }


def test_read_only_examples_do_not_import_robot_or_camera_drivers() -> None:
    paths = (
        ROOT / "examples/mujoco/replay_episode.py",
        ROOT / "integrations/ros2/joint_state_replay.py",
        ROOT / "integrations/ros2/prepare_description.py",
    )
    forbidden = ("lerobot.robots", "lerobot.cameras", "lerobot.teleoperators")
    for path in paths:
        imports = _imports(path)
        assert not any(name.startswith(forbidden) for name in imports), (path, imports)


def test_mujoco_sources_are_immutable_pins() -> None:
    pyproject = (ROOT / "examples/mujoco/pyproject.toml").read_text(encoding="utf-8")
    bootstrap = (ROOT / "examples/mujoco/bootstrap_model.ps1").read_text(encoding="utf-8")
    replay = (ROOT / "examples/mujoco/replay_episode.py").read_text(encoding="utf-8")
    assert "30da8e687a6dfc617fcd94afc367ac7071c376ce" in pyproject
    assert "lerobot[dataset]" in pyproject
    assert "mujoco==3.3.7" in pyproject
    assert "8161bba264d7fa7c99ca301e91e7fb44737676ad" in bootstrap
    assert "8161bba264d7fa7c99ca301e91e7fb44737676ad" in replay
    assert "robotstudio_so101" in bootstrap


@pytest.mark.parametrize("bad_time", [0.5, -0.5])
def test_ros_trajectory_requires_zero_start(tmp_path: Path, bad_time: float) -> None:
    module = _load_ros_module()
    path = tmp_path / "trajectory.jsonl"
    path.write_text(json.dumps(_trajectory_row(module, bad_time)), encoding="utf-8")
    with pytest.raises(ValueError, match="start at timestamp zero"):
        module.load_trajectory(path)


@pytest.mark.parametrize("second_time", [0.0, -0.1])
def test_ros_trajectory_requires_strict_time(tmp_path: Path, second_time: float) -> None:
    module = _load_ros_module()
    path = tmp_path / "trajectory.jsonl"
    rows = [
        _trajectory_row(module, 0.0, frame_index=0, expected_frames=2),
        _trajectory_row(module, second_time, frame_index=1, expected_frames=2),
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    with pytest.raises(ValueError, match="increase strictly"):
        module.load_trajectory(path)


@pytest.mark.parametrize("field", ["source_feature_names", "source_units", "model_joint_names"])
def test_ros_trajectory_rejects_reordered_contract_fields(tmp_path: Path, field: str) -> None:
    module = _load_ros_module()
    path = tmp_path / "trajectory.jsonl"
    row = _trajectory_row(module, 0.0)
    row[field] = list(reversed(row[field]))
    path.write_text(json.dumps(row), encoding="utf-8")
    with pytest.raises(ValueError, match="unexpected"):
        module.load_trajectory(path)


def test_ros_trajectory_rejects_partial_file_and_identity_change(tmp_path: Path) -> None:
    module = _load_ros_module()
    path = tmp_path / "trajectory.jsonl"
    path.write_text(
        json.dumps(_trajectory_row(module, 0.0, expected_frames=2)),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="incomplete"):
        module.load_trajectory(path)

    rows = [
        _trajectory_row(module, 0.0, frame_index=0, expected_frames=2),
        _trajectory_row(module, 0.1, frame_index=1, expected_frames=2),
    ]
    rows[1]["dataset_id"] = "local/other"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    with pytest.raises(ValueError, match="identity changed"):
        module.load_trajectory(path)


def test_ros_urdf_audit_counts_and_clips_explicitly(tmp_path: Path) -> None:
    module = _load_ros_module()
    joints = "".join(
        f'<joint name="{name}" type="revolute"><limit lower="-1" upper="1"/></joint>'
        for name in module.URDF_NAMES
    )
    urdf = tmp_path / "robot.urdf"
    urdf.write_text(f'<robot name="test">{joints}</robot>', encoding="utf-8")
    limits = module.load_urdf_limits(urdf)
    frame = module.TrajectoryFrame(0.0, (0.0, 0.0, 1.2, 0.0, 0.0, 0.0))
    counts = module.audit_urdf_limits([frame], limits)
    assert counts["Elbow"] == 1
    clipped = module.clip_to_urdf([frame], limits)
    assert clipped[0].positions_rad[2] == 1.0

    rounding_only = module.TrajectoryFrame(
        0.0,
        (0.0, 0.0, 1.0 + module.URDF_LIMIT_EPSILON_RAD / 2, 0.0, 0.0, 0.0),
    )
    assert module.audit_urdf_limits([rounding_only], limits)["Elbow"] == 0
    assert module.urdf_boundary_adjustments([rounding_only], limits)["Elbow"] == 1


def test_ros_description_output_is_local_and_atomically_complete(tmp_path: Path) -> None:
    module = _load_prepare_module()
    source = tmp_path / "source"
    (source / "urdf").mkdir(parents=True)
    (source / "meshes").mkdir()
    (source / "package.xml").write_text("<package/>", encoding="utf-8")
    (source / "urdf" / "so101_new_calib.urdf").write_text("<robot/>", encoding="utf-8")
    (source / "meshes" / "one.stl").write_text("solid one\nendsolid", encoding="utf-8")

    with pytest.raises(ValueError, match="project .local"):
        module.prepare(source, tmp_path / "outside", project_root=tmp_path)

    destination = tmp_path / ".local/ros2_ws/src/so_arm_description"
    result = module.prepare(source, destination, project_root=tmp_path)
    assert result["source_provenance"] == {
        "kind": "explicit_override",
        "verified_pin": False,
    }
    assert (destination / "CMakeLists.txt").is_file()
    assert (destination / "meshes" / "one.stl").is_file()
    assert not list(destination.parent.glob(".so_arm_description.*.tmp"))


def test_vision_geometry_config_remains_unmeasured_template() -> None:
    config = json.loads(
        (ROOT / "experiments/vision_geometry/config.example.json").read_text(encoding="utf-8")
    )
    assert config["camera_role"] == "front"
    assert config["charuco"]["square_length_m"] is None
    assert config["intrinsics_json"] is None
