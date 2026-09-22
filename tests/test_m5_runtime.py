from __future__ import annotations

import asyncio
import json
import math
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from fastapi.testclient import TestClient
from lelab import calibrate, record, rollout, server, teleoperate
from lelab.mode import HardwareLease, hardware_mode_gate
from pydantic import ValidationError


def _limits(value: float = 5.0) -> dict[str, float]:
    return {name: value for name in record.SO101_LIMIT_UNITS}


def _cameras() -> dict[str, dict[str, object]]:
    return {
        "arm": {"camera_index": 1, "width": 640, "height": 480, "fps": 30},
        "table_veiw": {"camera_index": 2, "width": 640, "height": 480, "fps": 30},
    }


def _request(**changes) -> record.RecordingRequest:
    data = {
        "leader_port": "FIXTURE-L",
        "follower_port": "FIXTURE-F",
        "leader_config": "leader.json",
        "follower_config": "follower.json",
        "dataset_repo_id": "fixture/session",
        "single_task": "fixture task",
        "num_episodes": 1,
        "episode_time_s": 1,
        "reset_time_s": 1,
        "fps": 15,
        "push_to_hub": False,
        "cameras": _cameras(),
        "max_relative_target": _limits(),
    }
    data.update(changes)
    return record.RecordingRequest(**data)


def _events() -> dict:
    return {
        "exit_early": False,
        "stop_recording": False,
        "rerecord_episode": False,
        "_decision": None,
        "_decision_lock": threading.Lock(),
        "_command_lock": threading.Lock(),
        "_stop_event": threading.Event(),
        "_phase_id": 0,
        "_phase_name": None,
        "_phase_open": False,
    }


class _Bus:
    def __init__(self):
        self.effects: list[str] = []

    def connect(self):
        self.effects.append("connect")

    def write_calibration(self, _calibration):
        self.effects.append("write_calibration")


class _Device:
    def __init__(self, name: str):
        self.name = name
        self.bus = _Bus()
        self.calibration = {}
        self.cameras = {}
        self.action_features = {}
        self.observation_features = {}
        self.sent = 0

    def configure(self):
        self.bus.effects.append("configure")

    def get_observation(self):
        return {}

    def send_action(self, action):
        self.sent += 1
        return action


class _Dataset:
    def __init__(self, fps: int = 15):
        self.fps = fps
        self.features = {
            "action": {"names": list(record.SO101_LIMIT_UNITS)},
            "observation.state": {"names": list(record.SO101_LIMIT_UNITS)},
        }
        self.num_episodes = 0
        self.num_frames = 0
        self.pending = 0
        self.saved = 0
        self.cleared = 0
        self.finalized = False

    def add_frame(self, _frame):
        self.pending += 1
        self.num_frames += 1

    def has_pending_frames(self):
        return self.pending > 0

    def save_episode(self):
        if not self.pending:
            raise AssertionError("zero-frame save")
        self.saved += 1
        self.num_episodes += 1
        self.pending = 0

    def clear_episode_buffer(self):
        self.cleared += 1
        self.pending = 0

    def finalize(self):
        self.finalized = True


def _cfg(num_episodes: int) -> SimpleNamespace:
    dataset = SimpleNamespace(
        repo_id="fixture/session",
        root=Path("fixture"),
        video=False,
        fps=15,
        num_episodes=num_episodes,
        episode_time_s=1,
        reset_time_s=1,
        single_task="fixture task",
        push_to_hub=False,
        private=False,
        tags=None,
        video_encoding_batch_size=1,
        rgb_encoder=None,
        depth_encoder=None,
        streaming_encoding=False,
        encoder_queue_maxsize=30,
        encoder_threads=None,
        num_image_writer_processes=0,
        num_image_writer_threads_per_camera=0,
    )
    return SimpleNamespace(
        robot=object(),
        teleop=object(),
        dataset=dataset,
        resume=False,
        display_data=False,
        play_sounds=False,
        _lelab_effective_config={},
    )


class M5RuntimeTests(unittest.TestCase):
    def setUp(self):
        hardware_mode_gate.reset_for_test()
        record.recording_counters = {
            "attempted": 0,
            "saved": 0,
            "accepted": 0,
            "timed_out": 0,
            "discarded": 0,
            "interrupted": 0,
        }
        record.current_end_reason = None
        record.saved_episodes = 0

    def tearDown(self):
        hardware_mode_gate.reset_for_test()
        teleoperate.teleoperation_active = False
        teleoperate._telemetry_snapshot = None
        teleoperate._teleoperation_lease = None
        teleoperate._teleoperation_last_session_id = None

    def test_unique_lease_blocks_delayed_aba_release(self):
        first, _ = hardware_mode_gate.claim("recording")
        self.assertIsNotNone(first)
        release_old = threading.Event()
        released: list[bool] = []

        def delayed_release():
            release_old.wait(2)
            released.append(hardware_mode_gate.release(first))

        worker = threading.Thread(target=delayed_release)
        worker.start()
        self.assertTrue(hardware_mode_gate.release(first))
        second, _ = hardware_mode_gate.claim("recording")
        self.assertIsNotNone(second)
        self.assertNotEqual(first.token, second.token)
        release_old.set()
        worker.join(timeout=2)
        self.assertEqual(released, [False])
        self.assertEqual(hardware_mode_gate.current_session_id(), second.token)

    def test_cleanup_fault_blocks_hardware_but_allows_shutdown_fence(self):
        lease, _ = hardware_mode_gate.claim("recording")
        self.assertIsNotNone(lease)
        self.assertTrue(hardware_mode_gate.mark_cleanup_fault(lease, "fixture close failure"))
        blocked, owner = hardware_mode_gate.claim("teleoperation")
        self.assertIsNone(blocked)
        self.assertEqual(owner, "cleanup_fault")
        shutdown, shutdown_owner = hardware_mode_gate.claim_shutdown()
        self.assertIsNotNone(shutdown)
        self.assertIsNone(shutdown_owner)
        self.assertTrue(hardware_mode_gate.release_shutdown(shutdown.token))

    def test_shutdown_fence_and_start_have_one_atomic_winner(self):
        barrier = threading.Barrier(2)
        winners: list[str] = []

        def claim_mode():
            barrier.wait()
            lease, _ = hardware_mode_gate.claim("recording")
            if lease:
                winners.append(lease.mode)

        def claim_shutdown():
            barrier.wait()
            lease, _ = hardware_mode_gate.claim_shutdown()
            if lease:
                winners.append(lease.mode)

        threads = [threading.Thread(target=claim_mode), threading.Thread(target=claim_shutdown)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
        self.assertEqual(len(winners), 1)

    def test_recording_request_rejects_nonfinite_wrong_or_extra_limits(self):
        for invalid in (
            {},
            {**_limits(), "extra": 1.0},
            {**_limits(), "gripper.pos": 1.0},
            {**_limits(), "gripper": math.inf},
            {**_limits(), "gripper": 0.0},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                _request(max_relative_target=invalid)

    def test_test_mode_is_rejected_before_any_device_constructor(self):
        payload = _request().model_dump(mode="json")
        payload["test_mode"] = True
        with (
            patch("lerobot.robots.make_robot_from_config") as robot_factory,
            patch("lerobot.teleoperators.make_teleoperator_from_config") as teleop_factory,
            patch("serial.Serial") as serial_constructor,
            patch("cv2.VideoCapture") as camera_constructor,
            TestClient(server.app, headers={"host": "localhost:8000"}) as client,
        ):
            response = client.post("/start-recording", json=payload)
        self.assertEqual(response.status_code, 422)
        robot_factory.assert_not_called()
        teleop_factory.assert_not_called()
        serial_constructor.assert_not_called()
        camera_constructor.assert_not_called()

    def test_stop_before_delayed_device_setup_constructs_no_hardware(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "HF_LEROBOT_HOME": str(Path(temporary) / "datasets"),
                "LELAB_RECORDING_EVIDENCE_ROOT": str(Path(temporary) / "evidence"),
            },
        ), patch.object(
            record, "setup_calibration_files", return_value=("leader", "follower")
        ), patch.object(
            record, "record_with_web_events"
        ) as record_worker, patch(
            "lerobot.robots.make_robot_from_config"
        ) as robot_factory, patch(
            "lerobot.teleoperators.make_teleoperator_from_config"
        ) as teleop_factory, patch(
            "serial.Serial"
        ) as serial_constructor, patch(
            "cv2.VideoCapture"
        ) as camera_constructor:
            request = _request()
            started = record.handle_start_recording(request)
            self.assertTrue(started["success"])
            stopped = record.handle_stop_recording(started["session_id"])
            self.assertTrue(stopped["success"])
            record.recording_thread.join(timeout=3)
            self.assertFalse(record.recording_thread.is_alive())

        record_worker.assert_not_called()
        robot_factory.assert_not_called()
        teleop_factory.assert_not_called()
        serial_constructor.assert_not_called()
        camera_constructor.assert_not_called()

    def test_zero_frame_session_is_not_reported_as_browseable(self):
        empty_dataset = SimpleNamespace(
            num_episodes=0,
            fps=15,
            features={},
            num_frames=0,
            meta=SimpleNamespace(robot_type="so101_follower"),
        )

        def no_frames(*_args, **_kwargs):
            record.recording_finalize_ok = True
            return empty_dataset

        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ,
            {
                "HF_LEROBOT_HOME": str(Path(temporary) / "datasets"),
                "LELAB_RECORDING_EVIDENCE_ROOT": str(Path(temporary) / "evidence"),
            },
        ), patch.object(
            record, "setup_calibration_files", return_value=("leader", "follower")
        ), patch.object(record, "record_with_web_events", side_effect=no_frames):
            started = record.handle_start_recording(_request())
            self.assertTrue(started["success"])
            record.recording_thread.join(timeout=3)
            self.assertFalse(record.recording_thread.is_alive())
            status = record.handle_recording_status(started["session_id"])
        self.assertTrue(status["session_ended"])
        self.assertFalse(status["dataset_usable"])
        self.assertEqual(status["outcome"], "cancelled_no_frames")

    def test_recording_controls_require_exact_session_and_return_http_conflict(self):
        lease = HardwareLease("recording", "current-session")
        events = _events()
        record.recording_active = True
        record.recording_events = events
        record._recording_lease = lease
        try:
            with TestClient(server.app, headers={"host": "localhost:8000"}) as client:
                stale = client.post("/stop-recording", json={"session_id": "old-session"})
                self.assertEqual(stale.status_code, 409)
                self.assertFalse(events["_stop_event"].is_set())
                current = client.post("/stop-recording", json={"session_id": lease.token})
            self.assertEqual(current.status_code, 200)
            self.assertTrue(current.json()["success"])
            self.assertTrue(events["_stop_event"].is_set())
        finally:
            record.recording_active = False
            record.recording_events = None
            record._recording_lease = None

    def test_recording_phase_controls_reject_stale_attempt_generation(self):
        lease = HardwareLease("recording", "current-session")
        events = _events()
        events.update({"_phase_id": 2, "_phase_name": "recording", "_phase_open": True})
        record.recording_active = True
        record.recording_events = events
        record._recording_lease = lease
        try:
            with TestClient(server.app, headers={"host": "localhost:8000"}) as client:
                stale = client.post(
                    "/recording-exit-early",
                    json={"session_id": lease.token, "phase_id": 1},
                )
                self.assertEqual(stale.status_code, 409)
                self.assertIsNone(events["_decision"])
                accepted = client.post(
                    "/recording-exit-early",
                    json={"session_id": lease.token, "phase_id": 2},
                )
                self.assertEqual(accepted.status_code, 200)
                self.assertEqual(events["_decision"], "accept")
                events.update({"_phase_id": 3, "_phase_name": "recording", "_decision": None})
                old_discard = client.post(
                    "/recording-rerecord-episode",
                    json={"session_id": lease.token, "phase_id": 2},
                )
                self.assertEqual(old_discard.status_code, 409)
                self.assertIsNone(events["_decision"])
        finally:
            record.recording_active = False
            record.recording_events = None
            record._recording_lease = None

    def test_phase_control_captured_before_rollover_cannot_mutate_new_phase(self):
        lease = HardwareLease("recording", "current-session")
        events = _events()
        events.update({"_phase_id": 1, "_phase_name": "recording", "_phase_open": True})
        record.recording_active = True
        record.recording_events = events
        record._recording_lease = lease
        captured = threading.Event()
        result: list[dict] = []
        real_context = record._control_context

        def capture_context(session_id: str):
            value = real_context(session_id)
            captured.set()
            return value

        events["_decision_lock"].acquire()
        try:
            with patch.object(record, "_control_context", side_effect=capture_context):
                worker = threading.Thread(
                    target=lambda: result.append(record.handle_exit_early(lease.token, 1))
                )
                worker.start()
                self.assertTrue(captured.wait(2))
                events.update({"_phase_id": 2, "_phase_name": "resetting", "_phase_open": True})
                events["_decision_lock"].release()
                worker.join(timeout=2)
        finally:
            if events["_decision_lock"].locked():
                events["_decision_lock"].release()
            record.recording_active = False
            record.recording_events = None
            record._recording_lease = None
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]["success"])
        self.assertEqual(events["_phase_id"], 2)
        self.assertIsNone(events["_decision"])

    def test_cross_mode_mutations_require_exact_session(self):
        teleop_lease = HardwareLease("teleoperation", "teleop-current")
        stop_event = threading.Event()
        teleoperate.teleoperation_active = True
        teleoperate._teleoperation_lease = teleop_lease
        teleoperate._teleoperation_stop_event = stop_event
        teleoperate.teleoperation_thread = None
        try:
            stale = teleoperate.handle_stop_teleoperation("teleop-old")
            self.assertFalse(stale["success"])
            self.assertFalse(stop_event.is_set())
            current = teleoperate.handle_stop_teleoperation(teleop_lease.token)
            self.assertTrue(current["success"])
            self.assertTrue(stop_event.is_set())
        finally:
            teleoperate.teleoperation_active = False
            teleoperate._teleoperation_lease = None
            teleoperate._teleoperation_stop_event = None
            teleoperate.teleoperation_thread = None

        manager = calibrate.CalibrationManager()
        calibration_lease = HardwareLease("calibration", "calibration-current")
        manager._lease = calibration_lease
        manager.status.calibration_active = True
        manager.status.status = "recording"
        manager.status.session_id = calibration_lease.token
        stale_step = manager.complete_step("calibration-old")
        self.assertFalse(stale_step["success"])
        self.assertFalse(manager._step_complete.is_set())
        current_step = manager.complete_step(calibration_lease.token)
        self.assertTrue(current_step["success"])
        self.assertTrue(manager._step_complete.is_set())

    def test_inference_stop_failure_keeps_exact_lease_owned(self):
        class StubbornProcess:
            def poll(self):
                return None

            def terminate(self):
                raise OSError("fixture terminate failure")

        lease, _ = hardware_mode_gate.claim("inference")
        self.assertIsNotNone(lease)
        proc = StubbornProcess()
        rollout.inference_active = True
        rollout._inference_proc = proc
        rollout._inference_lease = lease
        try:
            stale = rollout.handle_stop_inference("old-session")
            self.assertFalse(stale["success"])
            failed = rollout.handle_stop_inference(lease.token)
            self.assertFalse(failed["success"])
            self.assertIs(rollout._inference_proc, proc)
            self.assertEqual(hardware_mode_gate.current_session_id(), lease.token)
        finally:
            rollout.inference_active = False
            rollout._inference_proc = None
            rollout._inference_lease = None
            hardware_mode_gate.reset_for_test()

    def test_inference_exit_watcher_does_not_release_when_exit_is_unproven(self):
        class UnprovenProcess:
            def wait(self):
                raise OSError("fixture wait failure")

            def poll(self):
                return None

        lease, _ = hardware_mode_gate.claim("inference")
        proc = UnprovenProcess()
        rollout.inference_active = True
        rollout._inference_proc = proc
        rollout._inference_lease = lease
        try:
            rollout._release_mode_when_process_exits(proc, lease)
            self.assertTrue(rollout.inference_active)
            self.assertIs(rollout._inference_proc, proc)
            self.assertEqual(hardware_mode_gate.current_session_id(), lease.token)
        finally:
            rollout.inference_active = False
            rollout._inference_proc = None
            rollout._inference_lease = None
            hardware_mode_gate.reset_for_test()

    def test_inference_start_error_response_preserves_retained_session_id(self):
        retained = {
            "success": False,
            "status_code": 500,
            "message": "cleanup still running",
            "session_id": "retained-session",
        }
        payload = {
            "follower_port": "FIXTURE-F",
            "follower_config": "follower",
            "checkpoint_job_id": "act_fixture",
            "checkpoint_step": 12,
        }
        with (
            patch.object(
                server.job_registry,
                "resolve_checkpoint_ref_for_inference",
                return_value="local/checkpoint",
            ),
            patch.object(server, "handle_start_inference", return_value=retained),
            TestClient(server.app, headers={"host": "localhost:8000"}) as client,
        ):
            response = client.post("/start-inference", json=payload)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["session_id"], "retained-session")

    def test_websocket_broadcast_runs_on_the_connection_owner_loop(self):
        manager = server.ConnectionManager()
        sent = threading.Event()
        ready = threading.Event()
        owner_thread: list[int] = []
        send_thread: list[int] = []

        class Socket:
            async def accept(self):
                owner_thread.append(threading.get_ident())

            async def send_json(self, _data):
                send_thread.append(threading.get_ident())
                sent.set()

        socket = Socket()
        loop = asyncio.new_event_loop()

        def run_loop():
            asyncio.set_event_loop(loop)

            async def connect():
                await manager.connect(socket)
                ready.set()

            loop.create_task(connect())
            loop.run_forever()

        worker = threading.Thread(target=run_loop)
        worker.start()
        try:
            self.assertTrue(ready.wait(2))
            caller = threading.Thread(target=manager.broadcast_joint_data_sync, args=({"type": "fixture"},))
            caller.start()
            caller.join(timeout=2)
            self.assertTrue(sent.wait(2))
            self.assertEqual(send_thread, owner_thread)
        finally:
            manager.disconnect(socket)
            loop.call_soon_threadsafe(loop.stop)
            worker.join(timeout=2)
            loop.close()

    def test_websocket_joint_updates_are_filtered_by_exact_session(self):
        manager = server.ConnectionManager()

        class Socket:
            def __init__(self):
                self.sent = []

            async def accept(self):
                return None

            async def send_json(self, data):
                self.sent.append(data)

        current = Socket()
        stale = Socket()

        async def exercise():
            await manager.connect(current, "current-session")
            await manager.connect(stale, "old-session")
            await manager._send_to_all_connections(
                {"type": "joint_update", "session_id": "current-session", "joints": {}}
            )

        asyncio.run(exercise())
        self.assertEqual(len(current.sent), 1)
        self.assertEqual(stale.sent, [])

    def test_local_repo_id_gets_namespace_and_resume_keeps_exact_id(self):
        self.assertEqual(record._canonicalize_repo_id("my set"), "local/my_set")
        self.assertEqual(record._canonicalize_repo_id("local/exact_fixture"), "local/exact_fixture")
        for unsafe in ("../escape", "a/b/c", ""):
            with self.assertRaises(ValueError):
                record._canonicalize_repo_id(unsafe)

    def test_resume_uses_exact_local_root_and_rejects_profile_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dataset_dir = root / "local" / "resume_me"
            (dataset_dir / "meta").mkdir(parents=True)
            (dataset_dir / "meta" / "info.json").write_text(
                json.dumps({"total_episodes": 1, "fps": 15}), encoding="utf-8"
            )
            evidence = root / "evidence"
            with patch.dict(
                os.environ,
                {
                    "HF_LEROBOT_HOME": str(root),
                    "LELAB_RECORDING_EVIDENCE_ROOT": str(evidence),
                },
            ):
                original = _request(dataset_repo_id="local/resume_me")
                record._persist_profile(original)
                resume = _request(dataset_repo_id="local/resume_me", resume=True, num_episodes=2)
                with patch.object(record, "setup_calibration_files", return_value=("leader", "follower")):
                    config = record.create_record_config(resume)
                self.assertEqual(config.dataset.root, dataset_dir.resolve())
                changed = _request(dataset_repo_id="local/resume_me", resume=True, fps=16)
                with (
                    patch.object(record, "setup_calibration_files", return_value=("leader", "follower")),
                    self.assertRaisesRegex(ValueError, "changed recording profile"),
                ):
                    record.create_record_config(changed)

    def _run_state_machine(self, num_episodes: int, loop):
        dataset = _Dataset()
        robot = _Device("so101_follower")
        teleop = _Device("so101_leader")
        events = _events()
        lease = HardwareLease("recording", "fixture-session")
        request = _request(num_episodes=num_episodes)
        record.recording_config = request
        record.recording_active = True
        record.recording_events = events
        record._recording_lease = lease
        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"LELAB_RECORDING_EVIDENCE_ROOT": temporary}
        ), patch("lerobot.robots.make_robot_from_config", return_value=robot), patch(
            "lerobot.teleoperators.make_teleoperator_from_config", return_value=teleop
        ), patch(
            "lerobot.processor.make_default_processors", return_value=(object(), object(), object())
        ), patch(
            "lerobot.utils.feature_utils.hw_to_dataset_features", return_value={}
        ), patch(
            "lerobot.datasets.LeRobotDataset.create", return_value=dataset
        ), patch(
            "lerobot.scripts.lerobot_record.record_loop", side_effect=loop
        ), patch.object(
            record, "_persist_profile"
        ), patch.object(
            record,
            "safe_disconnect_device",
            return_value=SimpleNamespace(warnings=[], errors=[]),
        ), patch(
            "lerobot.utils.utils.log_say"
        ):
            try:
                result = record.record_with_web_events(_cfg(num_episodes), events, lease=lease)
            finally:
                record.recording_active = False
                record.recording_events = None
                record._recording_lease = None
        self.assertIs(result, dataset)
        self.assertTrue(dataset.finalized)
        return dataset, events

    def test_recording_cleanup_attempts_finalize_both_devices_and_trace_close(self):
        dataset = _Dataset()
        dataset.finalize = MagicMock(side_effect=RuntimeError("fixture finalize failure"))
        robot = _Device("so101_follower")
        teleop = _Device("so101_leader")
        events = _events()
        lease = HardwareLease("recording", "cleanup-session")
        request = _request()
        record.recording_config = request
        record.recording_active = True
        record.recording_events = events
        record._recording_lease = lease

        def loop(**kwargs):
            if kwargs.get("dataset") is not None:
                kwargs["dataset"].add_frame(
                    {"action": np.zeros(6), "observation.state": np.ones(6), "task": "fixture"}
                )

        cleanup = MagicMock(
            side_effect=[
                SimpleNamespace(warnings=[], errors=["fixture follower close failure"]),
                RuntimeError("fixture leader helper failure"),
            ]
        )
        original_trace_close = record._RecordingTrace.close

        def close_then_fail(trace):
            original_trace_close(trace)
            raise RuntimeError("fixture trace close failure")

        with tempfile.TemporaryDirectory() as temporary, patch.dict(
            os.environ, {"LELAB_RECORDING_EVIDENCE_ROOT": temporary}
        ), patch("lerobot.robots.make_robot_from_config", return_value=robot), patch(
            "lerobot.teleoperators.make_teleoperator_from_config", return_value=teleop
        ), patch(
            "lerobot.processor.make_default_processors", return_value=(object(), object(), object())
        ), patch(
            "lerobot.utils.feature_utils.hw_to_dataset_features", return_value={}
        ), patch(
            "lerobot.datasets.LeRobotDataset.create", return_value=dataset
        ), patch(
            "lerobot.scripts.lerobot_record.record_loop", side_effect=loop
        ), patch.object(record, "_persist_profile"), patch.object(
            record, "safe_disconnect_device", cleanup
        ), patch.object(
            record._RecordingTrace, "close", autospec=True, side_effect=close_then_fail
        ), patch("lerobot.utils.utils.log_say"):
            try:
                result = record.record_with_web_events(_cfg(1), events, lease=lease)
            finally:
                record.recording_active = False
                record.recording_events = None
                record._recording_lease = None

        self.assertIs(result, dataset)
        dataset.finalize.assert_called_once_with()
        self.assertEqual(cleanup.call_count, 2)
        self.assertTrue(any("dataset finalize failed" in item for item in record.recording_cleanup_errors))
        self.assertTrue(any("follower" in item for item in record.recording_device_cleanup_errors))
        self.assertTrue(any("leader" in item for item in record.recording_device_cleanup_errors))
        self.assertTrue(any("trace close failed" in item for item in record.recording_cleanup_errors))

    def test_stop_saves_nonempty_partial_and_never_resets_or_clears(self):
        calls: list[bool] = []

        def loop(**kwargs):
            calls.append(kwargs.get("dataset") is not None)
            kwargs["dataset"].add_frame(
                {"action": np.zeros(6), "observation.state": np.ones(6), "task": "fixture"}
            )
            kwargs["events"]["_stop_event"].set()

        dataset, _ = self._run_state_machine(3, loop)
        self.assertEqual(calls, [True])
        self.assertEqual(dataset.saved, 1)
        self.assertEqual(dataset.cleared, 0)
        self.assertEqual(record.recording_counters["interrupted"], 1)
        self.assertEqual(record.current_end_reason, "stop_interrupted_saved")

    def test_timeout_saves_and_finishes_without_automatic_rerecord(self):
        calls: list[bool] = []

        def loop(**kwargs):
            is_recording = kwargs.get("dataset") is not None
            calls.append(is_recording)
            if is_recording:
                kwargs["dataset"].add_frame(
                    {"action": np.zeros(6), "observation.state": np.ones(6), "task": "fixture"}
                )

        dataset, _ = self._run_state_machine(2, loop)
        self.assertEqual(calls, [True, False, True])
        self.assertEqual(dataset.saved, 2)
        self.assertEqual(dataset.cleared, 0)
        self.assertEqual(record.recording_counters["timed_out"], 2)

    def test_explicit_discard_is_only_clear_path_then_one_accept_saves(self):
        recording_attempt = 0

        def loop(**kwargs):
            nonlocal recording_attempt
            if kwargs.get("dataset") is None:
                return
            recording_attempt += 1
            kwargs["dataset"].add_frame(
                {"action": np.zeros(6), "observation.state": np.ones(6), "task": "fixture"}
            )
            with kwargs["events"]["_decision_lock"]:
                kwargs["events"]["_decision"] = "discard" if recording_attempt == 1 else "accept"

        dataset, _ = self._run_state_machine(1, loop)
        self.assertEqual(recording_attempt, 2)
        self.assertEqual(dataset.cleared, 1)
        self.assertEqual(dataset.saved, 1)
        self.assertEqual(record.recording_counters["discarded"], 1)
        self.assertEqual(record.recording_counters["accepted"], 1)

    def test_stop_after_observation_blocks_action_dispatch(self):
        stop_event = threading.Event()
        target = _Device("so101_follower")

        def observation():
            stop_event.set()
            return {"shoulder_pan.pos": 0.0}

        target.get_observation = observation
        trace = MagicMock()
        proxy = record._StopAwareRobot(target, stop_event, trace, threading.Lock())
        with self.assertRaises(record._StopRequestedError):
            proxy.get_observation()
        self.assertEqual(target.sent, 0)

    def test_official_action_remains_operator_target_while_effective_sent_is_traced(self):
        from lerobot.processor import make_default_processors
        from lerobot.scripts import lerobot_record

        names = list(record.SO101_LIMIT_UNITS)
        features = {
            "action": {"dtype": "float32", "shape": (6,), "names": [f"{name}.pos" for name in names]},
            "observation.state": {
                "dtype": "float32",
                "shape": (6,),
                "names": [f"{name}.pos" for name in names],
            },
        }

        class Robot:
            name = "so101_follower"

            def get_observation(self):
                return {f"{name}.pos": 1.0 for name in names}

            def send_action(self, action):
                return {key: 2.0 for key in action}

        class Teleop:
            def get_action(self):
                return {f"{name}.pos": 10.0 for name in names}

        class Dataset:
            fps = 1000

            def __init__(self):
                self.frames = []
                self.features = features

            def add_frame(self, frame):
                self.frames.append(frame)

        trace = MagicMock()
        robot_proxy = record._StopAwareRobot(Robot(), threading.Event(), trace, threading.Lock())
        dataset = Dataset()
        traced_dataset = record._TracingDataset(dataset, trace)
        processors = make_default_processors()
        events = {"exit_early": False}
        with patch.object(lerobot_record, "Teleoperator", Teleop):
            lerobot_record.record_loop(
                robot=robot_proxy,
                events=events,
                fps=1000,
                teleop_action_processor=processors[0],
                robot_action_processor=processors[1],
                robot_observation_processor=processors[2],
                teleop=Teleop(),
                dataset=traced_dataset,
                control_time_s=0.0001,
                single_task="fixture",
            )
        self.assertEqual(len(dataset.frames), 1)
        np.testing.assert_allclose(dataset.frames[0]["action"], np.full(6, 10.0))
        np.testing.assert_allclose(dataset.frames[0]["observation.state"], np.full(6, 1.0))
        traced_to_send, traced_effective = trace.command.call_args.args
        self.assertEqual(set(traced_to_send.values()), {10.0})
        self.assertEqual(set(traced_effective.values()), {2.0})

    def test_http_joint_positions_reads_worker_cache_only(self):
        robot = MagicMock()
        robot.get_observation.side_effect = AssertionError("serial read")
        teleoperate.current_robot = robot
        teleoperate.teleoperation_active = True
        teleoperate._teleoperation_lease = HardwareLease("teleoperation", "fixture")
        teleoperate._teleoperation_last_session_id = "fixture"
        teleoperate._telemetry_snapshot = {
            "status": "fresh",
            "joints": {"Rotation": 0.1},
            "units": {},
            "missing": [],
            "error": None,
            "timestamp": 1.0,
            "sequence": 1,
            "session_id": "fixture",
        }
        result = teleoperate.handle_get_joint_positions("fixture")
        self.assertTrue(result["success"])
        robot.get_observation.assert_not_called()

        stale = teleoperate.handle_get_joint_positions("old-session")
        self.assertFalse(stale["success"])
        status = teleoperate.handle_teleoperation_status("fixture")
        self.assertTrue(status["success"])
        self.assertEqual(status["session_id"], "fixture")

    def test_calibration_status_is_deep_copy_and_never_reads_bus(self):
        manager = calibrate.CalibrationManager()
        manager.status.status = "recording"
        manager.status.recorded_ranges = {"joint": {"min": 1, "max": 2, "current": 2}}
        manager.device = MagicMock()
        manager.device.bus.sync_read.side_effect = AssertionError("serial read")
        first = manager.get_status()
        first.recorded_ranges["joint"]["min"] = -1
        second = manager.get_status()
        self.assertEqual(second.recorded_ranges["joint"]["min"], 1)
        manager.device.bus.sync_read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
