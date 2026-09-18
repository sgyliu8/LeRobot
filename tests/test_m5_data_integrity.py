from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import av
import numpy as np
from fastapi.testclient import TestClient
from lelab import episode_media, record, server
from lerobot.configs.video import RGBEncoderConfig
from lerobot.datasets import LeRobotDataset
from torch.utils.data import DataLoader

from tools.audit_dataset import audit

JOINT_NAMES = [
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
    "gripper.pos",
]


class M5DataIntegrityTests(unittest.TestCase):
    def test_recording_profile_gate_rejects_schema_corruption_and_task_drift(self):
        request = record.RecordingRequest(
            leader_port="FIXTURE-L",
            follower_port="FIXTURE-F",
            leader_config="leader.json",
            follower_config="follower.json",
            dataset_repo_id="local/profile_fixture",
            single_task="move the fixture block",
            cameras={
                "arm": {"camera_index": 1, "width": 32, "height": 32, "fps": 30},
                "table_veiw": {"camera_index": 2, "width": 32, "height": 32, "fps": 30},
            },
            max_relative_target={
                "shoulder_pan": 5,
                "shoulder_lift": 5,
                "elbow_flex": 5,
                "wrist_flex": 5,
                "wrist_roll": 5,
                "gripper": 5,
            },
        )
        dataset = {
            "fps": 15,
            "cameras": ["arm", "table_veiw"],
            "episodes": [{"tasks": ["move the fixture block"]}],
        }
        profile = record._profile_payload(request)
        self.assertEqual(record.recording_profile_issues(request.dataset_repo_id, profile, dataset), [])

        bad_task = {**profile, "single_task": "different task"}
        self.assertIn(
            "recording profile single_task does not match every indexed episode",
            record.recording_profile_issues(request.dataset_repo_id, bad_task, dataset),
        )
        missing_robot = dict(profile)
        missing_robot.pop("robot")
        missing_issues = record.recording_profile_issues(request.dataset_repo_id, missing_robot, dataset)
        self.assertTrue(any("fields differ from schema" in issue for issue in missing_issues))
        self.assertIn("recording profile robot identity is incomplete", missing_issues)
        bad_encoder = {**profile, "rgb_encoder": {"vcodec": "h264"}}
        self.assertIn(
            "recording profile RGB encoder is not canonical",
            record.recording_profile_issues(request.dataset_repo_id, bad_encoder, dataset),
        )

    def test_real_short_h264_does_not_substitute_last_frame_past_eof(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "short.mp4"
            with av.open(str(path), mode="w") as container:
                stream = container.add_stream("h264", rate=15)
                stream.width = 32
                stream.height = 32
                stream.pix_fmt = "yuv420p"
                for value in (20, 200):
                    image = np.full((32, 32, 3), value, dtype=np.uint8)
                    frame = av.VideoFrame.from_ndarray(image, format="rgb24")
                    for packet in stream.encode(frame):
                        container.mux(packet)
                for packet in stream.encode():
                    container.mux(packet)

            with av.open(str(path)) as container:
                stream = container.streams.video[0]
                self.assertIsNone(episode_media._decode_at(container, stream, 10.0))

    def test_http_actual_id_offline_one_then_exact_resume_two_and_loader(self):
        fps = 15
        frames_per_episode = 2
        features = {
            "action": {"dtype": "float32", "shape": (6,), "names": JOINT_NAMES},
            "observation.state": {"dtype": "float32", "shape": (6,), "names": JOINT_NAMES},
            "observation.images.arm": {
                "dtype": "video",
                "shape": (32, 32, 3),
                "names": ["height", "width", "channels"],
            },
            "observation.images.table_veiw": {
                "dtype": "video",
                "shape": (32, 32, 3),
                "names": ["height", "width", "channels"],
            },
        }

        def payload(dataset_repo_id: str, *, resume: bool, episodes: int) -> dict:
            camera_backend = record._platform_backend().name if resume else None
            return {
                "leader_port": "FIXTURE-L",
                "follower_port": "FIXTURE-F",
                "leader_config": "leader.json",
                "follower_config": "follower.json",
                "dataset_repo_id": dataset_repo_id,
                "single_task": "move the fixture block",
                "num_episodes": episodes,
                "episode_time_s": 1,
                "reset_time_s": 1,
                "fps": fps,
                "video": True,
                "push_to_hub": False,
                "resume": resume,
                "streaming_encoding": True,
                "cameras": {
                    "arm": {
                        "camera_index": 1,
                        "width": 32,
                        "height": 32,
                        "fps": 30,
                        **({"backend": camera_backend} if camera_backend else {}),
                    },
                    "table_veiw": {
                        "camera_index": 2,
                        "width": 32,
                        "height": 32,
                        "fps": 30,
                        **({"backend": camera_backend} if camera_backend else {}),
                    },
                },
                "max_relative_target": {
                    "shoulder_pan": 5,
                    "shoulder_lift": 5,
                    "elbow_flex": 5,
                    "wrist_flex": 5,
                    "wrist_roll": 5,
                    "gripper": 5,
                },
                "rgb_encoder": {
                    "vcodec": "h264",
                    "pix_fmt": "yuv420p",
                    "video_backend": "pyav",
                    "crf": 23,
                    "g": 2,
                },
            }

        def synthetic_record(cfg, _events, *, lease):
            del lease
            encoder = cfg.dataset.rgb_encoder
            if cfg.resume:
                dataset = LeRobotDataset.resume(
                    cfg.dataset.repo_id,
                    root=cfg.dataset.root,
                    video_backend="pyav",
                    rgb_encoder=encoder,
                    streaming_encoding=True,
                    image_writer_processes=0,
                    image_writer_threads=0,
                )
            else:
                dataset = LeRobotDataset.create(
                    cfg.dataset.repo_id,
                    fps=cfg.dataset.fps,
                    features=features,
                    root=cfg.dataset.root,
                    robot_type="so101_follower",
                    use_videos=True,
                    rgb_encoder=encoder,
                    streaming_encoding=True,
                    image_writer_processes=0,
                    image_writer_threads=0,
                )
            for _ in range(cfg.dataset.num_episodes):
                episode_index = dataset.num_episodes
                for frame_index in range(frames_per_episode):
                    value = episode_index * 10 + frame_index
                    vector = np.full(6, value, dtype=np.float32)
                    dataset.add_frame(
                        {
                            "action": vector,
                            "observation.state": vector + 0.5,
                            "observation.images.arm": np.full((32, 32, 3), 30 + value, dtype=np.uint8),
                            "observation.images.table_veiw": np.full(
                                (32, 32, 3), 180 - value, dtype=np.uint8
                            ),
                            "task": cfg.dataset.single_task,
                        }
                    )
                dataset.save_episode(parallel_encoding=False)
            dataset.finalize()
            record._persist_profile(record.recording_config)
            record.recording_finalize_ok = True
            record.recording_counters.update(
                {
                    "attempted": cfg.dataset.num_episodes,
                    "saved": cfg.dataset.num_episodes,
                    "accepted": cfg.dataset.num_episodes,
                }
            )
            record.current_end_reason = "completed"
            return dataset

        with tempfile.TemporaryDirectory() as temporary:
            cache_root = Path(temporary) / "lerobot"
            evidence_root = Path(temporary) / "evidence"
            offline = {
                "HF_LEROBOT_HOME": str(cache_root),
                "LELAB_RECORDING_EVIDENCE_ROOT": str(evidence_root),
                "HF_HUB_OFFLINE": "1",
                "HF_DATASETS_OFFLINE": "1",
            }
            robot_constructor = MagicMock(side_effect=AssertionError("robot construction is forbidden"))
            teleop_constructor = MagicMock(side_effect=AssertionError("teleoperator construction is forbidden"))
            serial_constructor = MagicMock(side_effect=AssertionError("serial construction is forbidden"))
            camera_constructor = MagicMock(side_effect=AssertionError("camera construction is forbidden"))
            with patch.dict(os.environ, offline), patch.object(
                record, "setup_calibration_files", return_value=("leader", "follower")
            ), patch.object(
                record, "record_with_web_events", side_effect=synthetic_record
            ), patch(
                "lerobot.robots.make_robot_from_config", robot_constructor
            ), patch(
                "lerobot.teleoperators.make_teleoperator_from_config", teleop_constructor
            ), patch(
                "serial.Serial", serial_constructor
            ), patch(
                "cv2.VideoCapture", camera_constructor
            ), patch(
                "huggingface_hub.snapshot_download", side_effect=AssertionError("Hub access is forbidden")
            ), patch(
                "huggingface_hub.hf_hub_download", side_effect=AssertionError("Hub access is forbidden")
            ), patch(
                "lerobot.datasets.lerobot_dataset.snapshot_download",
                side_effect=AssertionError("LeRobot-bound Hub access is forbidden"),
            ), TestClient(server.app, headers={"host": "localhost:8000"}) as client:
                first_response = client.post(
                    "/start-recording", json=payload("m5_api_fixture", resume=False, episodes=1)
                )
                self.assertEqual(first_response.status_code, 200, first_response.text)
                first_start = first_response.json()
                actual_id = first_start["dataset_id"]
                self.assertTrue(actual_id.startswith("local/m5_api_fixture_"))
                self.assertEqual(first_start["effective_config"]["dataset_fps"], 15)
                self.assertEqual(first_start["effective_config"]["rgb_encoder"]["video_backend"], "pyav")
                self.assertEqual(
                    first_start["effective_config"]["cameras"]["arm"]["backend"],
                    record._platform_backend().name,
                )
                record.recording_thread.join(timeout=15)
                self.assertFalse(record.recording_thread.is_alive())
                first_status = client.get(
                    "/recording-status", params={"session_id": first_start["session_id"]}
                ).json()
                self.assertTrue(first_status["dataset_usable"], first_status)
                self.assertEqual(first_status["num_episodes"], 1)

                dataset_root = cache_root / actual_id
                initial = LeRobotDataset(actual_id, root=dataset_root, video_backend="pyav")
                batch = next(iter(DataLoader(initial, batch_size=2, num_workers=0)))
                self.assertEqual(tuple(batch["action"].shape), (2, 6))

                resume_response = client.post(
                    "/start-recording", json=payload(actual_id, resume=True, episodes=2)
                )
                self.assertEqual(resume_response.status_code, 200, resume_response.text)
                resume_start = resume_response.json()
                self.assertEqual(resume_start["dataset_id"], actual_id)
                self.assertEqual(resume_start["existing_episodes"], 1)
                self.assertEqual(resume_start["additional_episodes"], 2)
                self.assertEqual(resume_start["final_expected_episodes"], 3)
                record.recording_thread.join(timeout=15)
                self.assertFalse(record.recording_thread.is_alive())
                resume_status = client.get(
                    "/recording-status", params={"session_id": resume_start["session_id"]}
                ).json()
                self.assertTrue(resume_status["dataset_usable"], resume_status)
                self.assertEqual(resume_status["num_episodes"], 3)

                browse = client.get("/dataset-episodes", params={"repo_id": actual_id}).json()
                self.assertTrue(browse["complete"], browse)
                self.assertTrue(browse["resume_ready"], browse)
                self.assertEqual(browse["total_episodes"], 3)
                final = LeRobotDataset(actual_id, root=dataset_root, video_backend="pyav")
                final_batch = next(iter(DataLoader(final, batch_size=3, num_workers=0)))
                self.assertEqual(tuple(final_batch["action"].shape), (3, 6))

            robot_constructor.assert_not_called()
            teleop_constructor.assert_not_called()
            serial_constructor.assert_not_called()
            camera_constructor.assert_not_called()

    def test_offline_one_then_resume_two_real_videos_parquet_and_cpu_loader(self):
        repo_id = "local/m5_synthetic"
        fps = 15
        frames_per_episode = 3
        features = {
            "action": {"dtype": "float32", "shape": (6,), "names": JOINT_NAMES},
            "observation.state": {"dtype": "float32", "shape": (6,), "names": JOINT_NAMES},
            "observation.images.arm": {
                "dtype": "video",
                "shape": (32, 32, 3),
                "names": ["height", "width", "channels"],
            },
            "observation.images.table_veiw": {
                "dtype": "video",
                "shape": (32, 32, 3),
                "names": ["height", "width", "channels"],
            },
        }
        encoder = RGBEncoderConfig(
            vcodec="h264", pix_fmt="yuv420p", video_backend="pyav", crf=23, g=2
        )

        def add_episode(dataset: LeRobotDataset, episode: int) -> None:
            for frame_index in range(frames_per_episode):
                value = episode * 10 + frame_index
                vector = np.full(6, value, dtype=np.float32)
                dataset.add_frame(
                    {
                        "action": vector,
                        "observation.state": vector + 0.5,
                        "observation.images.arm": np.full(
                            (32, 32, 3), 30 + value, dtype=np.uint8
                        ),
                        "observation.images.table_veiw": np.full(
                            (32, 32, 3), 180 - value, dtype=np.uint8
                        ),
                        "task": "move the fixture block",
                    }
                )
            dataset.save_episode(parallel_encoding=False)

        with tempfile.TemporaryDirectory() as temporary:
            cache_root = Path(temporary) / "lerobot"
            dataset_root = cache_root / repo_id
            evidence_root = Path(temporary) / "evidence"
            offline = {
                "HF_LEROBOT_HOME": str(cache_root),
                "LELAB_RECORDING_EVIDENCE_ROOT": str(evidence_root),
                "HF_HUB_OFFLINE": "1",
                "HF_DATASETS_OFFLINE": "1",
            }
            with patch.dict(os.environ, offline), patch(
                "huggingface_hub.snapshot_download",
                side_effect=AssertionError("Hub access is forbidden"),
            ), patch(
                "huggingface_hub.hf_hub_download",
                side_effect=AssertionError("Hub access is forbidden"),
            ), patch(
                "lerobot.datasets.lerobot_dataset.snapshot_download",
                side_effect=AssertionError("LeRobot-bound Hub access is forbidden"),
            ):
                first = LeRobotDataset.create(
                    repo_id,
                    fps=fps,
                    features=features,
                    root=dataset_root,
                    robot_type="so101_follower",
                    use_videos=True,
                    rgb_encoder=encoder,
                    streaming_encoding=True,
                    image_writer_processes=0,
                    image_writer_threads=0,
                )
                add_episode(first, 0)
                first.finalize()

                initial = LeRobotDataset(repo_id, root=dataset_root, video_backend="pyav")
                self.assertEqual(initial.num_episodes, 1)
                self.assertEqual(initial.num_frames, frames_per_episode)
                batch = next(iter(DataLoader(initial, batch_size=2, num_workers=0)))
                self.assertEqual(tuple(batch["action"].shape), (2, 6))
                self.assertTrue(bool(batch["action"].isfinite().all()))
                self.assertIn("observation.images.arm", batch)
                self.assertIn("observation.images.table_veiw", batch)

                resumed = LeRobotDataset.resume(
                    repo_id,
                    root=dataset_root,
                    video_backend="pyav",
                    rgb_encoder=encoder,
                    streaming_encoding=True,
                    image_writer_processes=0,
                    image_writer_threads=0,
                )
                add_episode(resumed, 1)
                add_episode(resumed, 2)
                resumed.finalize()

                final = LeRobotDataset(repo_id, root=dataset_root, video_backend="pyav")
                self.assertEqual(final.num_episodes, 3)
                self.assertEqual(final.num_frames, 3 * frames_per_episode)
                self.assertEqual(
                    sorted({int(value) for value in final.hf_dataset["episode_index"]}),
                    [0, 1, 2],
                )
                final_batch = next(iter(DataLoader(final, batch_size=3, num_workers=0)))
                self.assertEqual(tuple(final_batch["action"].shape), (3, 6))
                self.assertTrue(bool(final_batch["observation.state"].isfinite().all()))

                before = {
                    path.relative_to(dataset_root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
                    for path in dataset_root.rglob("*")
                    if path.is_file()
                }
                record.last_recording_info = None
                info = record.handle_get_dataset_info(record.DatasetInfoRequest(dataset_repo_id=repo_id))
                after = {
                    path.relative_to(dataset_root).as_posix(): (path.stat().st_size, path.stat().st_mtime_ns)
                    for path in dataset_root.rglob("*")
                    if path.is_file()
                }
                self.assertTrue(info["success"])
                self.assertEqual(info["integrity_state"], "complete")
                self.assertEqual(info["num_episodes"], 3)
                self.assertEqual(info["cameras"], ["arm", "table_veiw"])
                self.assertEqual(before, after)

                request = record.RecordingRequest(
                    leader_port="FIXTURE-L",
                    follower_port="FIXTURE-F",
                    leader_config="leader.json",
                    follower_config="follower.json",
                    dataset_repo_id=repo_id,
                    single_task="move the fixture block",
                    num_episodes=1,
                    episode_time_s=1,
                    reset_time_s=1,
                    fps=fps,
                    cameras={
                        "arm": {"camera_index": 1, "width": 32, "height": 32, "fps": 30},
                        "table_veiw": {
                            "camera_index": 2,
                            "width": 32,
                            "height": 32,
                            "fps": 30,
                        },
                    },
                    max_relative_target={
                        "shoulder_pan": 5,
                        "shoulder_lift": 5,
                        "elbow_flex": 5,
                        "wrist_flex": 5,
                        "wrist_roll": 5,
                        "gripper": 5,
                    },
                )
                record._persist_profile(request)
                profile = record._profile_payload(request)

                with TestClient(server.app, headers={"host": "localhost:8000"}) as client:
                    browser_response = client.get(
                        "/dataset-episodes", params={"repo_id": repo_id}
                    )
                self.assertEqual(browser_response.status_code, 200)
                browser_payload = browser_response.json()
                self.assertTrue(browser_payload["success"])
                self.assertTrue(browser_payload["complete"])
                self.assertTrue(browser_payload["resume_ready"])
                self.assertEqual(browser_payload["total_episodes"], 3)
                self.assertEqual(browser_payload["recording_profile"], profile)

                def trace_frame(episode: int, frame_index: int, attempt_id: int, phase_id: int):
                    value = episode * 10 + frame_index
                    action = [float(value)] * 6
                    state = [float(value) + 0.5] * 6
                    command = {name: float(value) for name in JOINT_NAMES}
                    timing = {
                        "host_capture_completion_perf_counter_s": 100.0
                        + attempt_id
                        + frame_index / 30,
                        "arrival_age_at_observation_s": 0.001,
                        "reused_source_timestamp": False,
                        "timestamp_semantics": "host_post_capture_completion_not_exposure",
                        "association_semantics": (
                            "sampled_immediately_after_get_observation; exact frame identity unavailable"
                        ),
                    }
                    return {
                        "type": "frame",
                        "attempt_id": attempt_id,
                        "phase_id": phase_id,
                        "candidate_episode_index": episode,
                        "frame_index_within_attempt": frame_index,
                        "nominal_dataset_timestamp_s": frame_index / fps,
                        "loop_monotonic_s": 10.0 + frame_index / fps,
                        "inter_frame_interval_s": None if frame_index == 0 else 1 / fps,
                        "requested_processed_official_action": action,
                        "measured_state_pre_command": state,
                        "command": {
                            "to_send": command,
                            "effective_sent": command,
                            "clipped": {name: False for name in JOINT_NAMES},
                            "clipped_any": False,
                        },
                        "cameras": {"arm": dict(timing), "table_veiw": dict(timing)},
                    }

                def write_session(session_id: str, existing: int, episode_indices: list[int]):
                    rows = [
                        {
                            "type": "session_start",
                            "dataset_repo_id": repo_id,
                            "session_id": session_id,
                            "effective_config": {
                                **profile,
                                "resume": existing > 0,
                                "additional_episodes": len(episode_indices),
                                "push_to_hub": False,
                                "video": True,
                            },
                            "clock": "time.perf_counter",
                            "started_at_unix_s": 1000 + existing,
                            "existing_episodes": existing,
                        }
                    ]
                    for attempt_id, episode in enumerate(episode_indices, start=1):
                        phase_id = attempt_id * 2 - 1
                        rows.append(
                            {
                                "type": "attempt_start",
                                "attempt_id": attempt_id,
                                "phase_id": phase_id,
                                "candidate_episode_index": episode,
                                "monotonic_s": 10.0,
                            }
                        )
                        rows.extend(
                            trace_frame(episode, frame_index, attempt_id, phase_id)
                            for frame_index in range(frames_per_episode)
                        )
                        rows.append(
                            {
                                "type": "episode_end",
                                "attempt_id": attempt_id,
                                "phase_id": phase_id,
                                "candidate_episode_index": episode,
                                "saved_episode_index": episode,
                                "reason": "accept",
                                "saved": True,
                                "frames_observed": frames_per_episode,
                                "monotonic_s": 11.0,
                            }
                        )
                    rows.append(
                        {
                            "type": "session_end",
                            "end_reason": "completed",
                            "counters": {
                                "attempted": len(episode_indices),
                                "saved": len(episode_indices),
                                "accepted": len(episode_indices),
                                "timed_out": 0,
                                "discarded": 0,
                                "interrupted": 0,
                            },
                            "cleanup_warnings": [],
                            "cleanup_errors": [],
                        }
                    )
                    sidecar_dir = evidence_root / "sidecars" / session_id
                    sidecar_dir.mkdir(parents=True)
                    (sidecar_dir / "frames.jsonl").write_text(
                        "\n".join(json.dumps(row) for row in rows) + "\n",
                        encoding="utf-8",
                    )

                write_session("synthetic-session-1", 0, [0])
                write_session("synthetic-session-2", 1, [1, 2])
                unrelated = evidence_root / "sidecars" / "unrelated-interrupted"
                unrelated.mkdir(parents=True)
                (unrelated / "frames.jsonl").write_text('{"not":"finished"', encoding="utf-8")

                packed_location = episode_media.locate_episode_video(
                    dataset_root, 1, camera="arm"
                )
                self.assertEqual(packed_location.path, episode_media.locate_episode_video(
                    dataset_root, 2, camera="arm"
                ).path)
                with self.assertRaises(episode_media.EpisodeNotFoundError):
                    episode_media.extract_frame_png(packed_location, frames_per_episode)
                self.assertEqual(
                    [index for index, _ in episode_media.extract_thumbnails(
                        packed_location, [frames_per_episode - 1, frames_per_episode]
                    )],
                    [frames_per_episode - 1],
                )
                audited = audit(repo_id, ["arm", "table_veiw"])
                self.assertEqual(audited["status"], "PASS", audited)
                self.assertTrue(audited["read_only_manifest_unchanged"])

                sidecar_path = evidence_root / "sidecars" / "synthetic-session-2" / "frames.jsonl"
                original_sidecar = sidecar_path.read_text(encoding="utf-8")
                topology_rows = [
                    json.loads(line) for line in original_sidecar.splitlines() if line
                ]
                topology_rows[0]["existing_episodes"] = 0
                sidecar_path.write_text(
                    "\n".join(json.dumps(row) for row in topology_rows) + "\n",
                    encoding="utf-8",
                )
                topology_rejected = audit(repo_id, ["arm", "table_veiw"])
                self.assertEqual(topology_rejected["status"], "FAIL")
                self.assertTrue(
                    any("prior saved total" in failure for failure in topology_rejected["failures"]),
                    topology_rejected,
                )
                sidecar_path.write_text(original_sidecar, encoding="utf-8")

                broken_rows = [
                    json.loads(line)
                    for line in sidecar_path.read_text(encoding="utf-8").splitlines()
                    if line
                ]
                next(row for row in broken_rows if row.get("type") == "frame").pop("command")
                sidecar_path.write_text(
                    "\n".join(json.dumps(row) for row in broken_rows) + "\n",
                    encoding="utf-8",
                )
                rejected = audit(repo_id, ["arm", "table_veiw"])
                self.assertEqual(rejected["status"], "FAIL")
                self.assertTrue(
                    any("command provenance is missing" in failure for failure in rejected["failures"]),
                    rejected,
                )


if __name__ == "__main__":
    unittest.main()
