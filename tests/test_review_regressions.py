"""No-device regressions for issues reproduced in the end-to-end review."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from unittest.mock import MagicMock
from types import SimpleNamespace

import pytest


def test_importing_registry_never_migrates_cwd_jobs(tmp_path):
    source = tmp_path / "outputs/train/sentinel"
    source.mkdir(parents=True)
    (source / "keep.txt").write_text("preserve")
    target = tmp_path / "isolated"
    env = {**os.environ, "LELAB_OUTPUT_ROOT": str(target)}
    result = subprocess.run(
        [sys.executable, "-c", "import lelab.jobs"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert (source / "keep.txt").read_text() == "preserve"
    assert not (target / "sentinel").exists()


@pytest.mark.parametrize("processor", [{}, [], {"steps": [None]}, {"steps": [{"state_file": 123}]}])
def test_malformed_processor_is_unready_not_a_registry_crash(tmp_path, processor, monkeypatch):
    from lelab import jobs

    policy = tmp_path / "pretrained_model"
    policy.mkdir()
    (policy / "policy_preprocessor.json").write_text(json.dumps(processor))
    monkeypatch.setattr(jobs, "_check_safetensors", lambda *_args: None)
    model_ready, resume_ready, issues = jobs._assess_local_checkpoint(tmp_path)
    assert not model_ready and not resume_ready
    assert any("invalid pretrained_model/policy_preprocessor" in issue for issue in issues)


@pytest.mark.parametrize("duration", [0, -1, 601, 1.5, True, float("inf"), float("nan")])
def test_inference_must_have_a_finite_bounded_duration(duration):
    from lelab.rollout import InferenceRequest

    with pytest.raises(ValueError):
        InferenceRequest(
            follower_port="FIXTURE", follower_config="fixture",
            checkpoint_job_id="fixture", checkpoint_step=1, duration_s=duration,
        )


@pytest.mark.parametrize("limit", [float("inf"), float("nan"), {"gripper": float("inf")}])
def test_inference_limits_must_be_finite(limit):
    from lelab.rollout import InferenceRequest

    with pytest.raises(ValueError):
        InferenceRequest(
            follower_port="FIXTURE", follower_config="fixture",
            checkpoint_job_id="fixture", checkpoint_step=1, max_relative_target=limit,
        )


def test_start_inference_disables_implicit_fault_return(tmp_path, monkeypatch):
    from lelab import rollout
    from lelab.mode import hardware_mode_gate

    hardware_mode_gate.reset_for_test()
    proc = MagicMock()
    proc.poll.return_value = None
    spawn = MagicMock(return_value=proc)
    monkeypatch.setattr(rollout.subprocess, "Popen", spawn)
    monkeypatch.setattr(rollout, "_track_process_children", lambda _: None)
    monkeypatch.setattr(rollout.threading, "Thread", MagicMock())
    monkeypatch.setattr(rollout, "setup_follower_calibration_file", lambda _: "fixture")
    monkeypatch.setattr(rollout, "_resolve_policy_path", lambda _: str(tmp_path))
    monkeypatch.setattr(rollout.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(rollout, "_detect_device", lambda: "cpu")
    monkeypatch.setattr(rollout, "inference_active", False)
    monkeypatch.setattr(rollout, "_inference_lease", None)
    monkeypatch.setattr(rollout, "_inference_proc", None)
    try:
        result = rollout.handle_start_inference(rollout.InferenceRequest(
            follower_port="FIXTURE", follower_config="fixture",
            checkpoint_job_id="fixture", checkpoint_step=1,
        ), str(tmp_path))
        assert result["success"]
        assert "--return_to_initial_position=false" in spawn.call_args.args[0]
    finally:
        hardware_mode_gate.reset_for_test()


def test_parent_exit_does_not_release_a_live_owned_child():
    from lelab.rollout import _process_tree_exited

    proc = MagicMock()
    proc.poll.return_value = 1
    child = MagicMock()
    child.is_running.return_value = True
    proc._lelab_owned_children = {(123, 1.0): child}
    assert not _process_tree_exited(proc)
    child.is_running.return_value = False
    assert _process_tree_exited(proc)


def test_inference_stop_and_exit_watcher_share_stopped_outcome(monkeypatch):
    from lelab import rollout
    from lelab.mode import hardware_mode_gate

    hardware_mode_gate.reset_for_test()
    lease, _ = hardware_mode_gate.claim("inference")
    proc = MagicMock()
    proc.returncode = -15
    monkeypatch.setattr(rollout, "inference_active", True)
    monkeypatch.setattr(rollout, "_inference_proc", proc)
    monkeypatch.setattr(rollout, "_inference_lease", lease)
    monkeypatch.setattr(rollout, "_inference_last_status", None)
    monkeypatch.setattr(rollout, "_inference_meta", {})
    monkeypatch.setattr(rollout, "_process_tree_exited", lambda _: True)

    def concurrent_exit(_proc):
        assert rollout.handle_inference_status(lease.token)["outcome"] == "stopped"
        return True, None

    monkeypatch.setattr(rollout, "_terminate_process", concurrent_exit)
    try:
        assert rollout.handle_stop_inference(lease.token)["success"]
        assert rollout.handle_inference_status(lease.token)["outcome"] == "stopped"
    finally:
        hardware_mode_gate.reset_for_test()


@pytest.mark.parametrize("return_to_initial, expected_commands", [(True, 150), (False, 0)])
def test_pinned_rollout_fault_teardown_does_not_move_when_return_disabled(
    monkeypatch, return_to_initial, expected_commands,
):
    from lerobot.scripts import lerobot_rollout
    from lerobot.rollout.strategies.base import BaseStrategy
    from lerobot.rollout.configs import BaseStrategyConfig

    robot = MagicMock()
    robot.is_connected = True
    robot.get_observation.return_value = {"fixture.pos": 0.0}
    wrapper = SimpleNamespace(
        inner=robot, get_observation=robot.get_observation, send_action=robot.send_action,
    )
    cfg = SimpleNamespace(
        display_data=False, display_mode="fixture", strategy=SimpleNamespace(type="base"),
        robot=SimpleNamespace(type="fixture"), fps=30, duration=60,
        return_to_initial_position=return_to_initial,
    )
    ctx = SimpleNamespace(
        runtime=SimpleNamespace(cfg=cfg),
        hardware=SimpleNamespace(robot_wrapper=wrapper, initial_position={"fixture.pos": 1.0}, teleop=None),
    )
    strategy = BaseStrategy(BaseStrategyConfig())
    strategy._engine = MagicMock()
    strategy.setup = MagicMock()
    strategy.run = MagicMock(side_effect=TimeoutError("fixture motion timeout"))
    monkeypatch.setattr(lerobot_rollout, "init_logging", MagicMock())
    monkeypatch.setattr(lerobot_rollout, "ProcessSignalHandler", MagicMock())
    monkeypatch.setattr(lerobot_rollout, "build_rollout_context", lambda *_: ctx)
    monkeypatch.setattr(lerobot_rollout, "create_strategy", lambda _: strategy)
    monkeypatch.setattr("lerobot.rollout.strategies.core.precise_sleep", lambda _: None)
    with pytest.raises(TimeoutError, match="fixture motion timeout"):
        lerobot_rollout.rollout.__wrapped__(cfg)
    assert robot.send_action.call_count == expected_commands
    robot.disconnect.assert_called_once()


@pytest.mark.parametrize("state", ["done", "running"])
def test_restored_job_uses_new_root_without_reattaching_old_process(tmp_path, monkeypatch, state):
    from lelab import jobs
    from lelab.train import TrainingRequest

    folder = tmp_path / "jobs/restored"
    folder.mkdir(parents=True)
    record = jobs.JobRecord(
        id="restored", name="fixture", state=state, started_at=1,
        config=TrainingRequest(dataset_repo_id="fixture/dataset"),
        output_dir=str(tmp_path / "old-host/run"),
    )
    meta = folder / "job.json"
    meta.write_text(record.model_dump_json(), encoding="utf-8")
    original = meta.read_bytes()
    monkeypatch.setattr(jobs, "_process_status", lambda _: pytest.fail("old PID inspected"))
    reg = jobs.JobRegistry(folder.parent)
    try:
        restored = reg.get("restored")
        assert restored.output_dir == str(folder / "run")
        assert restored.state == ("interrupted" if state == "running" else state)
        assert meta.read_bytes() == original
    finally:
        reg.shutdown()
