"""Audit and publish a local SO101 trajectory as read-only ROS 2 state."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

SOURCE_FEATURE_NAMES = (
    "shoulder_pan.pos",
    "shoulder_lift.pos",
    "elbow_flex.pos",
    "wrist_flex.pos",
    "wrist_roll.pos",
    "gripper.pos",
)
SOURCE_UNITS = ("degree", "degree", "degree", "degree", "degree", "normalized_0_100")
MODEL_NAMES = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)
URDF_NAMES = ("Rotation", "Pitch", "Elbow", "Wrist_Pitch", "Wrist_Roll", "Jaw")
URDF_LIMIT_EPSILON_RAD = 1e-6


@dataclass(frozen=True)
class TrajectoryFrame:
    timestamp: float
    positions_rad: tuple[float, ...]


@dataclass(frozen=True)
class LoadedTrajectory:
    frames: tuple[TrajectoryFrame, ...]
    dataset_id: str
    episode: int
    expected_frames: int
    source_episode_arrays_sha256: str
    transform: dict[str, object]


def load_trajectory(path: Path) -> LoadedTrajectory:
    frames: list[TrajectoryFrame] = []
    identity: tuple[str, int, int, str, dict[str, object]] | None = None
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        data = json.loads(raw)
        if data.get("schema_version") != 2:
            raise ValueError(f"line {line_number}: unsupported trajectory schema")
        dataset_id = data.get("dataset_id")
        episode = data.get("episode")
        frame_index = data.get("frame_index")
        expected_frames = data.get("expected_frames")
        source_digest = data.get("source_episode_arrays_sha256")
        transform = data.get("transform")
        if not isinstance(dataset_id, str) or not dataset_id:
            raise ValueError(f"line {line_number}: missing dataset identity")
        if isinstance(episode, bool) or not isinstance(episode, int) or episode < 0:
            raise ValueError(f"line {line_number}: invalid episode identity")
        if frame_index != len(frames):
            raise ValueError(f"line {line_number}: frame_index must be contiguous from zero")
        if (
            isinstance(expected_frames, bool)
            or not isinstance(expected_frames, int)
            or expected_frames <= 0
        ):
            raise ValueError(f"line {line_number}: invalid expected_frames")
        if (
            not isinstance(source_digest, str)
            or len(source_digest) != 64
            or any(character not in "0123456789abcdef" for character in source_digest)
        ):
            raise ValueError(f"line {line_number}: invalid source episode digest")
        if not isinstance(transform, dict) or transform.get("kind") != "dataset_state_to_model_radians":
            raise ValueError(f"line {line_number}: invalid trajectory transform provenance")
        current_identity = (dataset_id, episode, expected_frames, source_digest, transform)
        if identity is None:
            identity = current_identity
        elif current_identity != identity:
            raise ValueError(f"line {line_number}: trajectory identity changed within the file")
        if tuple(data.get("source_feature_names", ())) != SOURCE_FEATURE_NAMES:
            raise ValueError(f"line {line_number}: unexpected or reordered source feature names")
        if tuple(data.get("source_units", ())) != SOURCE_UNITS:
            raise ValueError(f"line {line_number}: unexpected source units")
        if tuple(data.get("model_joint_names", ())) != MODEL_NAMES:
            raise ValueError(f"line {line_number}: unexpected or reordered model joint names")
        timestamp = float(data["timestamp"])
        positions = tuple(float(value) for value in data["positions_rad"])
        if len(positions) != 6 or not math.isfinite(timestamp) or not all(map(math.isfinite, positions)):
            raise ValueError(f"line {line_number}: expected finite timestamp and six positions")
        if not frames and abs(timestamp) > 1e-9:
            raise ValueError("trajectory must start at timestamp zero")
        if frames and timestamp <= frames[-1].timestamp:
            raise ValueError(f"line {line_number}: timestamp must increase strictly")
        frames.append(TrajectoryFrame(timestamp=timestamp, positions_rad=positions))
    if not frames:
        raise ValueError("trajectory is empty")
    assert identity is not None
    dataset_id, episode, expected_frames, source_digest, transform = identity
    if len(frames) != expected_frames:
        raise ValueError(
            f"trajectory is incomplete: expected {expected_frames} frames, found {len(frames)}"
        )
    return LoadedTrajectory(
        frames=tuple(frames),
        dataset_id=dataset_id,
        episode=episode,
        expected_frames=expected_frames,
        source_episode_arrays_sha256=source_digest,
        transform=transform,
    )


def load_urdf_limits(path: Path) -> dict[str, tuple[float, float]]:
    root = ET.parse(path).getroot()
    limits: dict[str, tuple[float, float]] = {}
    for name in URDF_NAMES:
        joint = root.find(f"./joint[@name='{name}']")
        if joint is None or joint.get("type") != "revolute":
            raise ValueError(f"URDF joint {name!r} must be a revolute joint")
        limit = joint.find("limit")
        if limit is None or limit.get("lower") is None or limit.get("upper") is None:
            raise ValueError(f"URDF joint {name!r} has no finite position limits")
        lower, upper = float(limit.get("lower")), float(limit.get("upper"))
        if not math.isfinite(lower) or not math.isfinite(upper) or lower >= upper:
            raise ValueError(f"URDF joint {name!r} has invalid position limits")
        limits[name] = (lower, upper)
    return limits


def audit_urdf_limits(
    frames: list[TrajectoryFrame],
    limits: dict[str, tuple[float, float]],
) -> dict[str, int]:
    return {
        name: sum(
            position < limits[name][0] - URDF_LIMIT_EPSILON_RAD
            or position > limits[name][1] + URDF_LIMIT_EPSILON_RAD
            for frame in frames
            for position in (frame.positions_rad[index],)
        )
        for index, name in enumerate(URDF_NAMES)
    }


def urdf_boundary_adjustments(
    frames: list[TrajectoryFrame],
    limits: dict[str, tuple[float, float]],
) -> dict[str, int]:
    return {
        name: sum(
            (
                position < limits[name][0]
                or position > limits[name][1]
            )
            and not (
                position < limits[name][0] - URDF_LIMIT_EPSILON_RAD
                or position > limits[name][1] + URDF_LIMIT_EPSILON_RAD
            )
            for frame in frames
            for position in (frame.positions_rad[index],)
        )
        for index, name in enumerate(URDF_NAMES)
    }


def clip_to_urdf(
    frames: list[TrajectoryFrame],
    limits: dict[str, tuple[float, float]],
) -> list[TrajectoryFrame]:
    return [
        TrajectoryFrame(
            timestamp=frame.timestamp,
            positions_rad=tuple(
                min(max(value, limits[name][0]), limits[name][1])
                for name, value in zip(URDF_NAMES, frame.positions_rad)
            ),
        )
        for frame in frames
    ]


def publish(frames: list[TrajectoryFrame], speed: float, ready_timeout: float) -> dict[str, object]:
    if not math.isfinite(speed) or speed <= 0:
        raise ValueError("speed must be a positive finite number")
    if not math.isfinite(ready_timeout) or ready_timeout <= 0:
        raise ValueError("ready-timeout must be a positive finite number")

    import rclpy
    from rosgraph_msgs.msg import Clock
    from sensor_msgs.msg import JointState

    wall_started = time.monotonic()
    rclpy.init()
    node = rclpy.create_node("so101_readonly_joint_state_replay")
    joint_publisher = node.create_publisher(JointState, "/joint_states", 10)
    clock_publisher = node.create_publisher(Clock, "/clock", 10)
    deadline = time.monotonic() + ready_timeout
    try:
        while (
            joint_publisher.get_subscription_count() == 0
            or clock_publisher.get_subscription_count() == 0
        ):
            if time.monotonic() >= deadline:
                raise TimeoutError("No subscribers became ready for /joint_states and /clock")
            rclpy.spin_once(node, timeout_sec=0.05)

        started = time.monotonic()
        for frame in frames:
            target = started + frame.timestamp / speed
            while time.monotonic() < target:
                rclpy.spin_once(node, timeout_sec=min(0.01, target - time.monotonic()))
            seconds = int(frame.timestamp)
            nanoseconds = round((frame.timestamp - seconds) * 1_000_000_000)
            if nanoseconds == 1_000_000_000:
                seconds += 1
                nanoseconds = 0

            clock = Clock()
            clock.clock.sec = seconds
            clock.clock.nanosec = nanoseconds
            clock_publisher.publish(clock)

            joints = JointState()
            joints.header.stamp = clock.clock
            joints.name = list(URDF_NAMES)
            joints.position = list(frame.positions_rad)
            joint_publisher.publish(joints)
            rclpy.spin_once(node, timeout_sec=0.0)
        flush_deadline = time.monotonic() + 0.25
        while time.monotonic() < flush_deadline:
            rclpy.spin_once(node, timeout_sec=0.01)
        return {
            "published_frames": len(frames),
            "topics": ["/clock", "/joint_states"],
            "ros_distro": os.environ.get("ROS_DISTRO"),
            "ros_domain_id": os.environ.get("ROS_DOMAIN_ID"),
            "speed": speed,
            "ready_timeout_s": ready_timeout,
            "wall_elapsed_s": time.monotonic() - wall_started,
        }
    finally:
        node.destroy_node()
        rclpy.shutdown()


def _prepare_report(path: Path | None, overwrite: bool) -> Path | None:
    if path is None:
        return None
    project_root = Path(__file__).resolve().parents[2]
    local_root = (project_root / ".local").resolve()
    resolved = path.expanduser().resolve()
    if resolved != local_root and local_root not in resolved.parents:
        raise ValueError("ROS reports must stay under the project .local directory")
    if resolved.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing report: {resolved}")
    return resolved


def _write_atomic(path: Path, payload: str, overwrite: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
            temporary.unlink()
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--urdf", type=Path, required=True)
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--ready-timeout", type=float, default=10.0)
    parser.add_argument("--clip-urdf", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--overwrite-report", action="store_true")
    args = parser.parse_args()

    trajectory_path = args.trajectory.resolve(strict=True)
    urdf_path = args.urdf.resolve(strict=True)
    report_path = _prepare_report(args.report, args.overwrite_report)
    trajectory = load_trajectory(trajectory_path)
    frames = list(trajectory.frames)
    limits = load_urdf_limits(urdf_path)
    violation_counts = audit_urdf_limits(frames, limits)
    boundary_adjustment_counts = urdf_boundary_adjustments(frames, limits)
    has_violations = any(violation_counts.values())
    report: dict[str, object] = {
        "status": "BLOCKED" if has_violations and not args.clip_urdf else "PASS",
        "mode": "audit_only" if args.audit_only else "ros2_publish",
        "frames": len(frames),
        "expected_frames": trajectory.expected_frames,
        "duration_s": frames[-1].timestamp,
        "timeline": "Dataset nominal frame timestamps",
        "dataset_id": trajectory.dataset_id,
        "episode": trajectory.episode,
        "source_episode_arrays_sha256": trajectory.source_episode_arrays_sha256,
        "trajectory_file_sha256": hashlib.sha256(trajectory_path.read_bytes()).hexdigest(),
        "trajectory_transform": trajectory.transform,
        "urdf_sha256": hashlib.sha256(urdf_path.read_bytes()).hexdigest(),
        "urdf_limit_violations": violation_counts,
        "urdf_boundary_adjustment_counts": boundary_adjustment_counts,
        "urdf_limit_epsilon_rad": URDF_LIMIT_EPSILON_RAD,
        "clip_urdf": bool(args.clip_urdf),
        "ros_domain_id": os.environ.get("ROS_DOMAIN_ID"),
        "speed": args.speed,
        "ready_timeout_s": args.ready_timeout,
        "wall_elapsed_s": None,
        "physical_registration": (
            "NOT_RUN: Dataset and URDF joint zero/sign conventions were not registered "
            "against the physical arm"
        ),
    }
    if has_violations and not args.clip_urdf:
        report["reason"] = (
            "Trajectory exceeds URDF limits; rerun with --clip-urdf "
            "for a marked visual derivative"
        )
    else:
        effective = (
            clip_to_urdf(frames, limits)
            if args.clip_urdf or any(boundary_adjustment_counts.values())
            else frames
        )
        if not args.audit_only:
            report.update(publish(effective, args.speed, args.ready_timeout))

    rendered = json.dumps(report, indent=2)
    print(rendered)
    if report_path:
        _write_atomic(report_path, rendered + "\n", args.overwrite_report)
    return 2 if report["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
