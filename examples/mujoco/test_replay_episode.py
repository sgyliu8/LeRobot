from __future__ import annotations

import json
from pathlib import Path

import mujoco
import numpy as np
import pytest
import replay_episode as replay


def test_joint_adapter_converts_six_finite_values() -> None:
    converted = replay._to_model_qpos(np.asarray([180.0, 90.0, 0.0, -90.0, -180.0, 100.0]))
    assert converted == pytest.approx([np.pi, np.pi / 2, 0.0, -np.pi / 2, -np.pi, np.deg2rad(100)])
    with pytest.raises(ValueError, match="six finite"):
        replay._to_model_qpos(np.asarray([0.0, 1.0]))
    with pytest.raises(ValueError, match="six finite"):
        replay._to_model_qpos(np.asarray([0.0, 0.0, 0.0, 0.0, 0.0, np.nan]))


def test_profile_is_exact_dataset_and_unit_authority(tmp_path: Path) -> None:
    profile = {
        "dataset_repo_id": "local/example",
        "dataset_fps": 15,
        "action_semantics": "processed_operator_target",
        "max_relative_target_units": replay.EXPECTED_UNITS,
    }
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    units, semantics, fps, digest = replay._load_profile(path, "local/example")
    assert units == replay.EXPECTED_UNITS
    assert semantics == "processed_operator_target"
    assert fps == 15
    assert len(digest) == 64
    with pytest.raises(ValueError, match="does not match"):
        replay._load_profile(path, "local/other")


def test_derived_outputs_cannot_overwrite_or_enter_dataset(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    with pytest.raises(ValueError, match="inside the source dataset"):
        replay._prepare_output(dataset / "report.json", dataset, False, tmp_path)
    with pytest.raises(ValueError, match="project .local"):
        replay._prepare_output(tmp_path / "outside.json", dataset, False, tmp_path)
    output = tmp_path / ".local/report.json"
    output.parent.mkdir()
    output.write_text("existing", encoding="utf-8")
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        replay._prepare_output(output, dataset, False, tmp_path)
    assert replay._prepare_output(output, dataset, True, tmp_path) == output.resolve()

    with pytest.raises(FileExistsError):
        replay._write_atomic(output, "replacement", False)
    assert output.read_text(encoding="utf-8") == "existing"
    assert not list(tmp_path.glob(".report.json.*.tmp"))


def test_pinned_scene_has_exact_joint_contract_and_experiment_objects() -> None:
    root = Path(__file__).resolve().parents[2]
    scene = root / ".local/upstream/mujoco_menagerie/robotstudio_so101/scene.xml"
    provenance = replay._verify_menagerie_source(scene.resolve(strict=True))
    assert provenance == {
        "origin": replay.MENAGERIE_ORIGIN,
        "commit": replay.MENAGERIE_COMMIT,
    }
    model = replay._load_experiment_model(scene)
    assert model.njnt == 6
    for name in replay.JOINT_NAMES:
        joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        assert joint >= 0
        assert model.jnt_type[joint] == mujoco.mjtJoint.mjJNT_HINGE
        assert model.jnt_limited[joint]
    assert mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "gripperframe") >= 0
    assert mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "experiment_table") >= 0
    assert mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "experiment_block") >= 0
