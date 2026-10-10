"""Synthetic H.264/Parquet only; device construction and Hub access are forbidden."""
from __future__ import annotations

import json

import numpy as np
import pytest

from so101_lab.data_preparation import (
    DatasetReview, EpisodeReview, assert_source_current, build_prepared_split,
    freeze_split, inspect_dataset, label_episode, preparation_path,
    preparation_summary, read_review, validate_prepared_split,
)
from so101_lab.data_preparation_cli import main
from so101_lab.training_split import bind_request, install_dataset_factory, parse_manifest
from tools.audit_dataset import EXPECTED_JOINT_NAMES, _manifest, _video_window_summary


@pytest.fixture(autouse=True)
def isolation(monkeypatch, tmp_path):
    import av
    import cv2
    import serial
    import huggingface_hub
    import lerobot.robots
    import lerobot.teleoperators
    import lerobot.datasets.lerobot_dataset as dataset_module

    def forbidden(*args, **kwargs):
        pytest.fail("device/network construction reached by offline preparation")

    for module, name in ((cv2, "VideoCapture"), (serial, "Serial"),
                         (lerobot.robots, "make_robot_from_config"),
                         (lerobot.teleoperators, "make_teleoperator_from_config"),
                         (huggingface_hub, "snapshot_download"), (huggingface_hub, "hf_hub_download"),
                         (dataset_module, "snapshot_download")):
        monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("HF_DATASETS_OFFLINE", "1")
    monkeypatch.setenv("HF_LEROBOT_HOME", str(tmp_path / "datasets"))
    monkeypatch.setenv("LELAB_RECORDING_EVIDENCE_ROOT", str(tmp_path / "evidence"))
    previous_level = av.logging.get_level()
    av.logging.set_level(av.logging.ERROR)
    yield
    av.logging.set_level(previous_level)


@pytest.fixture
def raw_dataset(tmp_path):
    from lelab import record
    from lerobot.configs.video import RGBEncoderConfig
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    repo = "fixture/episode_review"
    root = tmp_path / "datasets" / repo
    features = {name: {"dtype": "float32", "shape": (6,), "names": EXPECTED_JOINT_NAMES}
                for name in ("action", "observation.state")}
    features.update({f"observation.images.{key}": {
        "dtype": "video", "shape": (32, 32, 3), "names": ["height", "width", "channels"],
    } for key in ("arm", "table_veiw")})
    ds = LeRobotDataset.create(
        repo, fps=15, features=features, root=root, use_videos=True, streaming_encoding=True,
        rgb_encoder=RGBEncoderConfig(vcodec="h264", pix_fmt="yuv420p", crf=23, g=2),
        image_writer_processes=0, image_writer_threads=0,
    )
    for episode in range(4):
        for frame in range(4):
            values = np.full(6, episode * 20 + frame, dtype=np.float32)
            ds.add_frame({"action": values, "observation.state": values,
                          "observation.images.arm": np.full((32, 32, 3), episode * 50, dtype=np.uint8),
                          "observation.images.table_veiw": np.full((32, 32, 3), 250, dtype=np.uint8),
                          "task": "synthetic review fixture"})
        ds.save_episode(parallel_encoding=False)
    ds.finalize()
    request = record.RecordingRequest(
        leader_port="FIXTURE-L", follower_port="FIXTURE-F", leader_config="leader.json",
        follower_config="follower.json", dataset_repo_id=repo, single_task="synthetic review fixture",
        fps=15, num_episodes=4, episode_time_s=1, reset_time_s=1,
        cameras={key: {"camera_index": i, "width": 32, "height": 32, "fps": 30}
                 for i, key in enumerate(("arm", "table_veiw"))},
        max_relative_target={name.removesuffix(".pos"): 5 for name in EXPECTED_JOINT_NAMES},
    )
    record._persist_profile(request)
    profile = record._profile_payload(request)
    for session, episodes in (("session-train", [0, 1]), ("session-validation", [2]), ("session-test", [3])):
        rows = [{"type": "session_start", "dataset_repo_id": repo, "session_id": session,
                 "effective_config": {**profile, "resume": episodes[0] > 0,
                                      "additional_episodes": len(episodes), "push_to_hub": False, "video": True},
                 "clock": "time.perf_counter", "started_at_unix_s": 1000 + episodes[0],
                 "existing_episodes": episodes[0]}]
        for attempt, episode in enumerate(episodes, 1):
            phase = attempt * 2 - 1
            rows.append({"type": "attempt_start", "attempt_id": attempt, "phase_id": phase,
                         "candidate_episode_index": episode, "monotonic_s": 10.0})
            for frame in range(4):
                values = [float(episode * 20 + frame)] * 6
                targets = dict(zip(EXPECTED_JOINT_NAMES, values, strict=True))
                timing = {"host_capture_completion_perf_counter_s": 100.0 + attempt + frame / 30,
                          "arrival_age_at_observation_s": 0.001, "reused_source_timestamp": False,
                          "timestamp_semantics": "host_post_capture_completion_not_exposure",
                          "association_semantics": "sampled_immediately_after_get_observation; exact frame identity unavailable"}
                rows.append({"type": "frame", "attempt_id": attempt, "phase_id": phase,
                             "candidate_episode_index": episode, "frame_index_within_attempt": frame,
                             "nominal_dataset_timestamp_s": frame / 15, "loop_monotonic_s": 10.0 + frame / 15,
                             "inter_frame_interval_s": 1 / 15 if frame else None,
                             "requested_processed_official_action": values, "measured_state_pre_command": values,
                             "command": {"to_send": targets, "effective_sent": targets,
                                         "clipped": dict.fromkeys(EXPECTED_JOINT_NAMES, False), "clipped_any": False},
                             "cameras": {"arm": timing, "table_veiw": timing}})
            rows.append({"type": "episode_end", "attempt_id": attempt, "phase_id": phase,
                         "candidate_episode_index": episode, "saved_episode_index": episode,
                         "reason": "accept", "saved": True, "frames_observed": 4, "monotonic_s": 11.0})
        rows.append({"type": "session_end", "end_reason": "completed", "cleanup_warnings": [], "cleanup_errors": [],
                     "counters": {"attempted": len(episodes), "saved": len(episodes), "accepted": len(episodes),
                                  "timed_out": 0, "discarded": 0, "interrupted": 0}})
        path = tmp_path / "evidence/sidecars" / session / "frames.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return repo, root


def reviewed(repo):
    report = inspect_dataset(repo)
    assert report["status"] == "PASS", report["failures"]
    for episode in range(4):
        label_episode(repo, episode, decision="exclude" if episode in (1, 2) else "keep",
                      outcome="failure" if episode in (1, 2) else "success", intervention=False,
                      reason="synthetic human decision, not a real demonstration")
    return freeze_split(repo, {"session-validation"}, {"session-test"})


def test_complete_review_to_official_parser_loader_and_cpu_batch(raw_dataset, monkeypatch, tmp_path):
    import draccus
    import torch
    from lelab.train import TrainingRequest, build_training_command
    from lerobot.configs.train import TrainPipelineConfig
    from lerobot.datasets import factory
    import lerobot.policies.act.configuration_act  # noqa: F401

    repo, root = raw_dataset
    before = _manifest(root)
    split = reviewed(repo)
    assert split.normalization_stats_source.episode_indices == [0]
    assert split.excluded_training_episodes == [1]
    assert [x.episode_index for x in split.partitions["validation"]] == [2]  # failed held-out attempt retained
    request, snapshot = bind_request(TrainingRequest(dataset_repo_id=repo, policy_chunk_size=2, policy_n_action_steps=1))
    assert request.dataset_task == "data_review_v1" and request.dataset_episodes == [0]
    cfg = draccus.parse(TrainPipelineConfig, args=build_training_command(request, str(tmp_path / "run"))[3:])
    cfg.validate()
    monkeypatch.setattr(factory, "make_train_eval_datasets", factory.make_train_eval_datasets)
    install_dataset_factory(snapshot, tmp_path / "receipt.json")
    train, validation = factory.make_train_eval_datasets(cfg)
    assert train.episodes == [0] and validation.episodes == [2]
    for dataset in (train, validation):
        np.testing.assert_allclose(dataset.meta.stats["action"]["mean"], np.full(6, 1.5))
        batch = next(iter(torch.utils.data.DataLoader(dataset, batch_size=1, num_workers=0)))
        assert batch["action"].isfinite().all()
        assert batch["observation.images.arm"].shape[-3:] == (3, 32, 32)
    receipt = json.loads((tmp_path / "receipt.json").read_text())
    assert receipt["test_episodes_loaded"] == []
    assert receipt["reviewed_source_sha256"] == split.source_sha256
    assert parse_manifest(split.model_dump_json()) == split
    assert _manifest(root) == before
    assert preparation_summary(repo)["status"] == "FROZEN"
    with pytest.raises(ValueError, match="frozen"):
        label_episode(repo, 0, reason="late edit")
    # A resume uses the same private job snapshot, not a newly supplied episode list.
    job_snapshot = tmp_path / "training_split.json"
    job_snapshot.write_text(split.model_dump_json(), encoding="utf-8")
    assert bind_request(request, source=job_snapshot)[1] == split
    with pytest.raises(ValueError, match="differ"):
        bind_request(request.model_copy(update={"dataset_episodes": [0, 1]}))


def test_inspect_cli_pending_gate_visual_hints_and_failed_refresh(raw_dataset):
    from lelab.train import TrainingRequest

    repo, root = raw_dataset
    before = _manifest(root)
    assert main(["inspect", repo]) == 0
    assert main(["status", repo]) == 0
    assert preparation_summary(repo)["pending"] == 4
    with pytest.raises(ValueError, match="Freeze"):
        bind_request(TrainingRequest(dataset_repo_id=repo))
    assert main(["freeze", repo, "--validation-session", "session-validation", "--test-session", "session-test"]) == 1
    assert main(["label", repo, "--episode", "0", "--decision", "keep", "--outcome", "success",
                 "--intervention", "no", "--reason", "synthetic reviewed"]) == 0
    assert main(["inspect", repo]) == 1
    hint = _video_window_summary(root, 0, "arm")["visual_review_hints"]
    assert hint["sample_count"] == 4 and hint["median"]["dark_fraction"] > 0.99
    assert _manifest(root) == before
    # Corrupt only the disposable fixture, never the user's original media.
    path = next(root.glob("videos/observation.images.arm/**/*.mp4"))
    path.write_bytes(b"not an mp4")
    broken_before = _manifest(root)
    assert main(["inspect", repo, "--refresh"]) == 1
    assert preparation_summary(repo)["status"] == "AUDIT_FAILED"
    with pytest.raises(ValueError, match="technical audit"):
        freeze_split(repo, {"session-validation"}, {"session-test"})
    assert _manifest(root) == broken_before
    assert list(preparation_path(repo).parent.glob("history/*-review.json"))


def test_changed_source_or_root_cannot_reuse_admission(raw_dataset, tmp_path):
    from lelab.train import TrainingRequest

    repo, root = raw_dataset
    split = reviewed(repo)
    with pytest.raises(ValueError, match="root differs"):
        bind_request(TrainingRequest(dataset_repo_id=repo, dataset_root=str(tmp_path / "other")))
    path = root / "meta/stats.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="changed"):
        assert_source_current(split.review)
    with pytest.raises(ValueError, match="changed"):
        bind_request(TrainingRequest(dataset_repo_id=repo))


def test_session_leakage_pending_and_forged_selection_rejected():
    review = DatasetReview(dataset_repo_id="fixture/review", source_sha256="a" * 64,
                          profile_sha256="b" * 64, audit_status="PASS", episodes=[
        EpisodeReview(episode_index=i, session_id=f"session-{i}", decision="keep", outcome="success",
                      intervention=False, reason="fixture") for i in range(3)
    ])
    for val, test in (({"session-1"}, {"session-1"}), ({"missing"}, {"session-2"}), (set(), {"session-2"})):
        with pytest.raises(ValueError):
            build_prepared_split(review, val, test)
    same_session = review.model_copy(deep=True)
    for item in same_session.episodes:
        item.session_id = "one-session"
    with pytest.raises(ValueError, match="empty"):
        build_prepared_split(same_session, set(), {"one-session"})
    split = build_prepared_split(review, {"session-1"}, {"session-2"})
    split.review.episodes[0].outcome = "failure"
    with pytest.raises(ValueError):
        validate_prepared_split(split)
    for index in (True, -1, "1", 1.5):
        with pytest.raises(ValueError):
            EpisodeReview(episode_index=index, session_id="session")
    with pytest.raises(ValueError, match="known outcome"):
        EpisodeReview(episode_index=0, session_id="session", decision="keep", reason="unknown")


def test_no_local_dataset_does_not_break_existing_training_request(tmp_path):
    from lelab.train import TrainingRequest

    request = TrainingRequest(dataset_repo_id="fixture/not_downloaded")
    assert bind_request(request) == (request, None)


def test_real_job_entry_and_browse_bind_review_without_starting_training(raw_dataset, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from lelab import jobs, server
    from lelab.train import TrainingRequest

    repo, _ = raw_dataset
    split = reviewed(repo)
    launched = []
    # Intercept the actual process-launch boundary, not a test_mode flag.
    monkeypatch.setattr(jobs.LocalJobRunner, "start", lambda _self, _id, config, _output: launched.append(config))
    monkeypatch.setattr(jobs, "_validate_windows_checkpoint_path_budget", lambda _: None)
    registry = jobs.JobRegistry(tmp_path / "jobs")
    try:
        job = registry.start(TrainingRequest(dataset_repo_id=repo, policy_device="cpu"))
        assert launched[0].dataset_episodes == [0]
        assert launched[0].dataset_task == "data_review_v1"
        saved = tmp_path / "jobs" / job.id / "training_split.json"
        assert parse_manifest(saved.read_text(encoding="utf-8")) == split
    finally:
        registry.shutdown()
    with TestClient(server.app, headers={"host": "localhost:8000"}) as client:
        response = client.get("/dataset-episodes", params={"repo_id": repo})
        assert response.status_code == 200
        assert response.json()["data_preparation"]["status"] == "FROZEN"


def test_portable_identity_and_unsafe_output_guard(raw_dataset, monkeypatch, tmp_path):
    import shutil

    repo, root = raw_dataset
    split = reviewed(repo)
    destination = tmp_path / "moved/datasets"
    evidence = tmp_path / "moved/evidence"
    shutil.copytree(root, destination / repo)
    shutil.copytree(tmp_path / "evidence", evidence)
    monkeypatch.setenv("HF_LEROBOT_HOME", str(destination))
    monkeypatch.setenv("LELAB_RECORDING_EVIDENCE_ROOT", str(evidence))
    assert_source_current(split.review)
    assert read_review(repo) == split.review
    monkeypatch.setenv("LELAB_RECORDING_EVIDENCE_ROOT", str(destination / repo / "inside-raw"))
    with pytest.raises(ValueError, match="outside the raw"):
        preparation_path(repo)
