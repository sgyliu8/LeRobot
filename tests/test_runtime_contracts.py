from __future__ import annotations

import math
import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from lelab import record, server, teleoperate
from lelab.mode import hardware_mode_gate
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect


class _Robot:
    def __init__(self, observation=None, error: Exception | None = None):
        self.observation = observation
        self.error = error

    def get_observation(self):
        if self.error is not None:
            raise self.error
        return self.observation


class RuntimeContractTests(unittest.TestCase):
    def setUp(self):
        hardware_mode_gate.reset_for_test()
        teleoperate.teleoperation_active = False
        record.recording_active = False

    def tearDown(self):
        hardware_mode_gate.reset_for_test()
        teleoperate.teleoperation_active = False
        record.recording_active = False

    def test_health_and_static_ui_do_not_construct_robot(self):
        with patch.object(teleoperate, "SO101Follower") as follower, TestClient(
            server.app, headers={"host": "localhost:8000"}
        ) as client:
            health = client.get("/health")
            root = client.get("/", headers={"accept": "text/html"})
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json(), {"status": "ok", "message": "FastAPI server is running"})
        self.assertEqual(root.status_code, 200)
        self.assertIn("<div id=\"root\"></div>", root.text)
        follower.assert_not_called()

    def test_untrusted_origin_and_host_are_rejected_before_write(self):
        with TestClient(server.app, headers={"host": "localhost:8000"}) as client:
            self.assertEqual(client.get("/health", headers={"host": "evil.example"}).status_code, 400)
            with patch.object(server, "save_robot_port") as save_robot_port:
                response = client.post(
                    "/save-robot-port",
                    headers={"origin": "https://evil.example"},
                    json={"robot_type": "leader", "port": "FIXTURE"},
                )
        self.assertEqual(response.status_code, 403)
        save_robot_port.assert_not_called()

    def test_untrusted_websocket_origin_is_rejected(self):
        with (
            TestClient(server.app, headers={"host": "localhost:8000"}) as client,
            self.assertRaises(WebSocketDisconnect) as caught,
            client.websocket_connect(
                "/ws/joint-data",
                headers={"origin": "https://evil.example"},
            ),
        ):
            self.fail("untrusted WebSocket was accepted")
        self.assertEqual(caught.exception.code, 1008)

    def test_mode_gate_has_one_atomic_winner(self):
        barrier = threading.Barrier(8)
        results: list[bool] = []
        results_lock = threading.Lock()

        def claim():
            barrier.wait()
            lease, _ = hardware_mode_gate.claim("teleoperation")
            with results_lock:
                results.append(lease is not None)

        threads = [threading.Thread(target=claim) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)

        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 7)

    def test_mode_gate_rejects_repeat_and_allows_retry_after_release(self):
        lease, owner = hardware_mode_gate.claim("teleoperation")
        self.assertIsNotNone(lease)
        self.assertIsNone(owner)

        rejected, owner = hardware_mode_gate.claim("teleoperation")
        self.assertIsNone(rejected)
        self.assertEqual(owner, "teleoperation")
        rejected, owner = hardware_mode_gate.claim("recording")
        self.assertIsNone(rejected)
        self.assertEqual(owner, "teleoperation")

        other, _ = hardware_mode_gate.claim("recording")
        self.assertIsNone(other)
        self.assertFalse(hardware_mode_gate.release(type(lease)("recording", lease.token)))
        self.assertTrue(hardware_mode_gate.release(lease))
        next_lease, owner = hardware_mode_gate.claim("recording")
        self.assertIsNotNone(next_lease)
        self.assertIsNone(owner)

    def test_other_mode_blocks_before_hardware_setup(self):
        lease, _ = hardware_mode_gate.claim("calibration")
        self.assertIsNotNone(lease)
        request = teleoperate.TeleoperateRequest(
            leader_port="FIXTURE-L",
            follower_port="FIXTURE-F",
            leader_config="leader.json",
            follower_config="follower.json",
            max_relative_target={name: 5.0 for name in record.SO101_LIMIT_UNITS},
        )
        with patch.object(teleoperate, "setup_calibration_files") as setup:
            result = teleoperate.handle_start_teleoperation(request)
        self.assertFalse(result["success"])
        self.assertIn("Calibration", result["message"])
        setup.assert_not_called()

    def test_relative_target_reaches_runtime_config(self):
        request = record.RecordingRequest(
            leader_port="FIXTURE-L",
            follower_port="FIXTURE-F",
            leader_config="leader.json",
            follower_config="follower.json",
            dataset_repo_id="fixture/dataset",
            single_task="fixture only",
            cameras={
                "arm": {"camera_index": 1, "width": 640, "height": 480, "fps": 30},
                "table_veiw": {"camera_index": 2, "width": 640, "height": 480, "fps": 30},
            },
            max_relative_target={name: 5.0 for name in record.SO101_LIMIT_UNITS},
        )
        with patch.object(record, "setup_calibration_files", return_value=("leader", "follower")):
            config = record.create_record_config(request)
        self.assertEqual(config.robot.max_relative_target, {name: 5.0 for name in record.SO101_LIMIT_UNITS})

    def test_relative_target_must_be_positive(self):
        with self.assertRaises(ValidationError):
            teleoperate.TeleoperateRequest(
                leader_port="FIXTURE-L",
                follower_port="FIXTURE-F",
                leader_config="leader.json",
                follower_config="follower.json",
                max_relative_target=0,
            )

    def test_telemetry_preserves_units_and_omits_missing_values(self):
        telemetry = teleoperate.get_joint_telemetry_from_robot(
            _Robot({"shoulder_pan.pos": 10.0, "gripper.pos": 50.0})
        )
        self.assertEqual(telemetry["status"], "partial")
        self.assertEqual(telemetry["units"]["shoulder_pan.pos"], "degree")
        self.assertEqual(telemetry["units"]["gripper.pos"], "normalized_0_100")
        self.assertAlmostEqual(telemetry["joints"]["Rotation"], math.radians(10.0))
        self.assertAlmostEqual(telemetry["joints"]["Jaw"], math.radians(50.0))
        self.assertNotIn("Pitch", telemetry["joints"])
        self.assertIn("shoulder_lift.pos", telemetry["missing"])

    def test_telemetry_error_is_not_zero_filled(self):
        telemetry = teleoperate.get_joint_telemetry_from_robot(_Robot(error=RuntimeError("fixture")))
        self.assertEqual(telemetry["status"], "error")
        self.assertEqual(telemetry["joints"], {})
        self.assertEqual(telemetry["error"], "fixture")


if __name__ == "__main__":
    unittest.main()
