"""Strictly read-only audit for one local M5 LeRobot Dataset v3 recording.

The audit never calls repair, resume, delete, or a Hub API. Optional JSON output
is restricted to the ignored ``LELAB_RECORDING_EVIDENCE_ROOT`` tree.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import av
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from lelab.episode_media import (
    UnsafeDatasetPathError,
    ensure_safe_dataset_path,
    iter_safe_files,
    list_cameras,
    locate_episode_video,
    read_episode_index,
    read_info,
    resolve_dataset_dir,
)

EXPECTED_JOINT_KEYS = [
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
]
EXPECTED_JOINT_NAMES = [f"{name}.pos" for name in EXPECTED_JOINT_KEYS]
EXPECTED_UNITS = {
    **{name: "degree" for name in EXPECTED_JOINT_KEYS[:5]},
    "gripper": "normalized_0_100",
}
REQUIRED_PARQUET_COLUMNS = {
    "action",
    "observation.state",
    "episode_index",
    "frame_index",
    "timestamp",
    "index",
    "task_index",
}
EPISODE_END_SAVED = {
    "accept": True,
    "timeout": True,
    "discard": False,
    "stop_interrupted": True,
    "stop_no_frames": False,
}


def _evidence_root() -> Path:
    configured = os.environ.get("LELAB_RECORDING_EVIDENCE_ROOT")
    root = Path(configured) if configured else Path.cwd() / ".local" / "evidence" / "recordings"
    return root.expanduser().resolve()


def _manifest(root: Path) -> dict[str, tuple[int, int, str]]:
    result: dict[str, tuple[int, int, str]] = {}
    for path in iter_safe_files(root):
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        stat = path.stat()
        result[path.relative_to(root).as_posix()] = (stat.st_size, stat.st_mtime_ns, digest.hexdigest())
    return result


def _feature_names(info: dict[str, Any], key: str) -> list[str]:
    feature = (info.get("features") or {}).get(key) or {}
    return [str(name) for name in feature.get("names") or []]


def _finite_vector(value: Any, *, width: int = 6) -> np.ndarray | None:
    try:
        array = np.asarray(value, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        return None
    if array.size != width or not np.isfinite(array).all():
        return None
    return array


def _finite_joint_map(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict) or set(value) != set(EXPECTED_JOINT_NAMES):
        return None
    normalized: dict[str, float] = {}
    for key, raw in value.items():
        if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
            return None
        normalized[key] = float(raw)
    return normalized


def _read_parquet_rows(dataset_dir: Path) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    tables: list[pa.Table] = []
    available: set[str] = set()
    for path in iter_safe_files(dataset_dir / "data", suffix=".parquet"):
        table = pq.read_table(path)
        available.update(table.column_names)
        tables.append(table)
    if not tables:
        return [], available, set()
    common = set(tables[0].column_names)
    for table in tables[1:]:
        common &= set(table.column_names)
    selected = sorted(REQUIRED_PARQUET_COLUMNS & common)
    rows = pa.concat_tables([table.select(selected) for table in tables]).to_pylist()
    return rows, available, common


def _required_int(row: dict[str, Any], key: str) -> int:
    value = row[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def _parse_parquet_rows(
    rows: list[dict[str, Any]],
    *,
    fps: int,
    declared_frames: int,
    failures: list[str],
) -> dict[int, list[dict[str, Any]]]:
    parsed: list[tuple[int, int, int, int, dict[str, Any]]] = []
    for row_number, row in enumerate(rows):
        try:
            episode_index = _required_int(row, "episode_index")
            frame_index = _required_int(row, "frame_index")
            global_index = _required_int(row, "index")
            task_index = _required_int(row, "task_index")
            raw_timestamp = row["timestamp"]
            if isinstance(raw_timestamp, bool) or not isinstance(raw_timestamp, (int, float)):
                raise TypeError("timestamp must be numeric")
            timestamp = float(raw_timestamp)
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            failures.append(f"Parquet row {row_number}: invalid index/time fields: {exc}")
            continue
        if episode_index < 0 or frame_index < 0 or global_index < 0:
            failures.append(f"Parquet row {row_number}: episode/frame/global indices must be non-negative")
        if not math.isfinite(timestamp) or fps <= 0 or not math.isclose(
            timestamp, frame_index / fps, rel_tol=0.0, abs_tol=1e-5
        ):
            failures.append(f"Parquet row {row_number}: timestamp is not frame_index/fps")
        if task_index < 0:
            failures.append(f"Parquet row {row_number}: task_index is negative")
        if _finite_vector(row.get("action")) is None or _finite_vector(row.get("observation.state")) is None:
            failures.append(f"Parquet row {row_number}: action/state is not a finite six-value vector")

        normalized = dict(row)
        normalized.update(
            episode_index=episode_index,
            frame_index=frame_index,
            index=global_index,
            task_index=task_index,
            timestamp=timestamp,
        )
        parsed.append((global_index, episode_index, frame_index, task_index, normalized))

    parsed.sort(key=lambda item: item[0])
    if [item[0] for item in parsed] != list(range(declared_frames)):
        failures.append("global Parquet index is not contiguous")

    by_episode: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for _, episode_index, _, _, row in parsed:
        by_episode[episode_index].append(row)
    return by_episode


def _validate_episode_end_semantics(row: dict[str, Any], label: str, failures: list[str]) -> None:
    reason = row.get("reason")
    saved = row.get("saved") is True
    expected_saved = EPISODE_END_SAVED.get(reason)
    if expected_saved is None:
        failures.append(f"{label}: unknown episode_end reason {reason!r}")
    elif saved is not expected_saved:
        failures.append(f"{label}: reason {reason!r} requires saved={expected_saved}")


def _profile_path(repo_id: str) -> Path:
    digest = hashlib.sha256(repo_id.encode("utf-8")).hexdigest()
    return _evidence_root() / "profiles" / f"{digest}.json"


def _load_profile(repo_id: str, failures: list[str]) -> dict[str, Any] | None:
    path = _profile_path(repo_id)
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        failures.append("frozen local recording profile is missing")
        return None
    except (OSError, json.JSONDecodeError) as exc:
        failures.append(f"frozen local recording profile is unreadable: {exc}")
        return None
    if not isinstance(profile, dict) or profile.get("dataset_repo_id") != repo_id:
        failures.append("recording profile identity does not match dataset")
        return None
    return profile


def _validate_profile(
    profile: dict[str, Any] | None,
    info: dict[str, Any],
    expected_cameras: list[str],
    failures: list[str],
) -> None:
    if profile is None:
        return
    fps = int(info.get("fps") or 0)
    if profile.get("schema_version") != 2:
        failures.append("recording profile schema_version must be 2")
    if profile.get("dataset_fps") != fps:
        failures.append(f"profile fps {profile.get('dataset_fps')} != Dataset fps {fps}")
    if profile.get("video") is not True:
        failures.append("recording profile video must be true")
    if profile.get("push_to_hub") is not False:
        failures.append("recording profile push_to_hub must be false")
    if not isinstance(profile.get("single_task"), str) or not profile["single_task"].strip():
        failures.append("recording profile task is empty")
    if set(profile.get("max_relative_target") or {}) != set(EXPECTED_JOINT_KEYS):
        failures.append("recording profile target limits do not use exactly six bare SO-101 keys")
    elif any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
        for value in profile["max_relative_target"].values()
    ):
        failures.append("recording profile target limits must be finite and positive")
    if profile.get("max_relative_target_units") != EXPECTED_UNITS:
        failures.append("recording profile target-limit units are missing or incorrect")
    cameras = profile.get("cameras") or {}
    if sorted(cameras) != sorted(expected_cameras):
        failures.append(f"profile camera keys {sorted(cameras)} != expected {sorted(expected_cameras)}")
    indices = [str(camera.get("camera_index")) for camera in cameras.values() if isinstance(camera, dict)]
    if len(indices) != len(cameras) or len(set(indices)) != len(indices):
        failures.append("profile camera indices are missing or not distinct")
    encoder = profile.get("rgb_encoder") or {}
    if (
        encoder.get("vcodec") != "h264"
        or encoder.get("pix_fmt") != "yuv420p"
        or encoder.get("video_backend") != "pyav"
        or not isinstance(encoder.get("crf"), int)
        or not 0 <= encoder["crf"] <= 51
        or encoder.get("g") != 2
    ):
        failures.append("recording profile is not the supported H.264/yuv420p/PyAV GOP-2 contract")
    if profile.get("action_semantics") != "processed_operator_target":
        failures.append("recording profile action semantics are incorrect")
    if profile.get("timestamp_semantics") != "nominal_frame_index_div_dataset_fps":
        failures.append("recording profile timestamp semantics are incorrect")
    robot = profile.get("robot")
    expected_robot_keys = {"leader_port", "follower_port", "leader_config", "follower_config"}
    if (
        not isinstance(robot, dict)
        or set(robot) != expected_robot_keys
        or not all(isinstance(value, str) and value for value in robot.values())
    ):
        failures.append("recording profile robot identity is missing or incomplete")


def _video_window_summary(dataset_dir: Path, episode_idx: int, camera: str) -> dict[str, Any]:
    location = locate_episode_video(dataset_dir, episode_idx, camera=camera)
    video_path = ensure_safe_dataset_path(dataset_dir, location.path, require_file=True)
    decoded = 0
    times: list[float] = []
    with av.open(str(video_path)) as container:
        stream = container.streams.video[0]
        codec = stream.codec_context.name
        pixel_format = stream.codec_context.pix_fmt
        width, height = stream.codec_context.width, stream.codec_context.height
        average_rate = float(stream.average_rate) if stream.average_rate else None
        start = location.from_timestamp or 0.0
        end = location.to_timestamp
        for frame in container.decode(stream):
            if frame.time is None:
                continue
            stamp = float(frame.time)
            if stamp + 1e-6 < start:
                continue
            if end is not None and stamp >= end:
                break
            times.append(stamp)
            decoded += 1
    return {
        "path": video_path.relative_to(dataset_dir).as_posix(),
        "codec": codec,
        "pixel_format": pixel_format,
        "width": width,
        "height": height,
        "average_rate": average_rate,
        "decoded_frames": decoded,
        "pts_monotonic": all(b > a for a, b in itertools.pairwise(times)),
        "from_timestamp": location.from_timestamp,
        "to_timestamp": location.to_timestamp,
    }


def _rate_summary(stamps: list[float]) -> dict[str, float | int | None]:
    unique = sorted(set(stamps))
    deltas = [b - a for a, b in itertools.pairwise(unique) if b > a]
    return {
        "unique_updates": len(unique),
        "measured_hz": (1.0 / statistics.mean(deltas)) if deltas else None,
    }


def _validate_command(row: dict[str, Any], label: str, failures: list[str]) -> None:
    if _finite_vector(row.get("requested_processed_official_action")) is None:
        failures.append(f"{label}: missing/non-finite six-value official action")
    if _finite_vector(row.get("measured_state_pre_command")) is None:
        failures.append(f"{label}: missing/non-finite six-value pre-command state")
    command = row.get("command")
    if not isinstance(command, dict):
        failures.append(f"{label}: command provenance is missing")
        return
    to_send = _finite_joint_map(command.get("to_send"))
    effective = _finite_joint_map(command.get("effective_sent"))
    clipped = command.get("clipped")
    clipped_any = command.get("clipped_any")
    if to_send is None or effective is None:
        failures.append(f"{label}: to_send/effective_sent must contain six finite joint targets")
        return
    if not isinstance(clipped, dict) or set(clipped) != set(EXPECTED_JOINT_NAMES) or not all(
        isinstance(value, bool) for value in clipped.values()
    ):
        failures.append(f"{label}: clipped flags must cover six joints")
        return
    expected_clipped = {
        key: to_send[key] != effective[key]
        for key in EXPECTED_JOINT_NAMES
    }
    if clipped != expected_clipped or clipped_any is not any(expected_clipped.values()):
        failures.append(f"{label}: clipped flags do not match requested versus effective targets")


def _sidecar_summary(
    repo_id: str,
    profile: dict[str, Any] | None,
    expected_cameras: list[str],
    parquet_by_episode: dict[int, list[dict[str, Any]]],
    failures: list[str],
) -> dict[str, Any] | None:
    sessions: list[tuple[float, str, list[dict[str, Any]]]] = []
    for path in sorted((_evidence_root() / "sidecars").glob("*/frames.jsonl")):
        try:
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
        except OSError:
            # An unreadable sidecar cannot be attributed to this dataset.
            continue
        if not lines:
            continue
        try:
            first = json.loads(lines[0])
        except json.JSONDecodeError:
            # Ownership is unknown until a valid session_start is read. Do not
            # let an unrelated interrupted dataset poison this dataset's audit.
            continue
        if first.get("type") != "session_start" or first.get("dataset_repo_id") != repo_id:
            continue
        try:
            rows = [first, *(json.loads(line) for line in lines[1:])]
        except json.JSONDecodeError as exc:
            failures.append(f"sidecar {path.parent.name} is unreadable after its matching session_start: {exc}")
            continue
        raw_started = first.get("started_at_unix_s")
        if (
            isinstance(raw_started, bool)
            or not isinstance(raw_started, (int, float))
            or not math.isfinite(raw_started)
        ):
            failures.append(f"sidecar {path.parent.name}: started_at_unix_s must be finite")
            started = 0.0
        else:
            started = float(raw_started)
        sessions.append((started, path.parent.name, rows))
    sessions.sort()
    if not sessions:
        failures.append("no matching local timing/action sidecar")
        return None

    saved_attempts: dict[int, tuple[str, int, list[dict[str, Any]]]] = {}
    session_summaries: list[dict[str, Any]] = []
    expected_existing_episodes = 0
    for _, folder_session, rows in sessions:
        starts = [row for row in rows if row.get("type") == "session_start"]
        ends = [row for row in rows if row.get("type") == "session_end"]
        if len(starts) != 1 or len(ends) != 1:
            failures.append(f"session {folder_session}: requires exactly one session_start and session_end")
            continue
        start = starts[0]
        if start.get("session_id") != folder_session:
            failures.append(f"session {folder_session}: embedded session_id mismatch")
        effective = start.get("effective_config")
        expected_effective_keys = set(profile or {}) | {"resume", "additional_episodes", "push_to_hub", "video"}
        if not isinstance(effective, dict) or set(effective) != expected_effective_keys:
            failures.append(f"session {folder_session}: effective runtime config keys are incomplete or unexpected")
        elif profile is not None and any(effective.get(key) != value for key, value in profile.items()):
            failures.append(f"session {folder_session}: effective runtime config differs from frozen profile")

        existing = start.get("existing_episodes")
        if existing != expected_existing_episodes:
            failures.append(
                f"session {folder_session}: existing_episodes {existing!r} != prior saved total "
                f"{expected_existing_episodes}"
            )
        additional_requested = effective.get("additional_episodes") if isinstance(effective, dict) else None
        if not isinstance(additional_requested, int) or isinstance(additional_requested, bool) or additional_requested < 1:
            failures.append(f"session {folder_session}: additional_episodes must be a positive integer")
        if isinstance(effective, dict):
            if effective.get("resume") is not (expected_existing_episodes > 0):
                failures.append(f"session {folder_session}: resume flag does not match existing episode count")
            if effective.get("push_to_hub") is not False:
                failures.append(f"session {folder_session}: push_to_hub must be false")
            if effective.get("video") is not True:
                failures.append(f"session {folder_session}: video must be true")

        attempts: dict[int, dict[str, Any]] = {}
        for row in rows:
            kind = row.get("type")
            attempt_id = row.get("attempt_id")
            if kind == "attempt_start":
                if not isinstance(attempt_id, int) or attempt_id < 1 or attempt_id in attempts:
                    failures.append(f"session {folder_session}: invalid/duplicate attempt_id {attempt_id!r}")
                    continue
                attempts[attempt_id] = {"start": row, "frames": [], "end": None}
            elif kind == "frame":
                if attempt_id not in attempts:
                    failures.append(f"session {folder_session}: frame references unknown attempt {attempt_id!r}")
                    continue
                attempts[attempt_id]["frames"].append(row)
            elif kind == "episode_end":
                if attempt_id not in attempts or attempts[attempt_id]["end"] is not None:
                    failures.append(f"session {folder_session}: invalid end for attempt {attempt_id!r}")
                    continue
                attempts[attempt_id]["end"] = row

        attempt_summaries: list[dict[str, Any]] = []
        session_saved_indices: list[int] = []
        reason_counts = {"accepted": 0, "timed_out": 0, "discarded": 0, "interrupted": 0}
        for attempt_id, attempt in sorted(attempts.items()):
            start_row = attempt["start"]
            frames = attempt["frames"]
            end_row = attempt["end"]
            label = f"session {folder_session} attempt {attempt_id}"
            if end_row is None:
                failures.append(f"{label}: missing episode_end")
                continue
            if [frame.get("frame_index_within_attempt") for frame in frames] != list(range(len(frames))):
                failures.append(f"{label}: frame indices are not contiguous")
            phase_id = start_row.get("phase_id")
            candidate = start_row.get("candidate_episode_index")
            intervals: list[float] = []
            camera_stamps: dict[str, list[float]] = defaultdict(list)
            for frame_index, frame in enumerate(frames):
                frame_label = f"{label} frame {frame_index}"
                if frame.get("phase_id") != phase_id or frame.get("candidate_episode_index") != candidate:
                    failures.append(f"{frame_label}: phase/candidate identity changed")
                nominal = frame.get("nominal_dataset_timestamp_s")
                dataset_fps = int((profile or {}).get("dataset_fps") or 0)
                if (
                    dataset_fps <= 0
                    or not isinstance(nominal, (int, float))
                    or not math.isclose(float(nominal), frame_index / dataset_fps, rel_tol=0.0, abs_tol=1e-6)
                ):
                    failures.append(f"{frame_label}: invalid nominal Dataset timestamp")
                _validate_command(frame, frame_label, failures)
                interval = frame.get("inter_frame_interval_s")
                if frame_index == 0:
                    if interval is not None:
                        failures.append(f"{frame_label}: first interval must be null")
                elif not isinstance(interval, (int, float)) or not math.isfinite(interval) or interval <= 0:
                    failures.append(f"{frame_label}: loop interval must be finite and positive")
                else:
                    intervals.append(float(interval))
                camera_timing = frame.get("cameras")
                if not isinstance(camera_timing, dict) or set(camera_timing) != set(expected_cameras):
                    failures.append(f"{frame_label}: camera timing keys are missing or changed")
                    continue
                for camera in expected_cameras:
                    timing = camera_timing[camera]
                    stamp = timing.get("host_capture_completion_perf_counter_s") if isinstance(timing, dict) else None
                    if (
                        not isinstance(stamp, (int, float))
                        or not math.isfinite(stamp)
                        or timing.get("timestamp_semantics") != "host_post_capture_completion_not_exposure"
                        or timing.get("association_semantics")
                        != "sampled_immediately_after_get_observation; exact frame identity unavailable"
                    ):
                        failures.append(f"{frame_label}: invalid {camera} host timing semantics")
                    else:
                        camera_stamps[camera].append(float(stamp))

            if end_row.get("frames_observed") != len(frames):
                failures.append(f"{label}: episode_end frame count mismatch")
            saved = end_row.get("saved") is True
            saved_index = end_row.get("saved_episode_index")
            if saved:
                if not isinstance(saved_index, int) or saved_index in saved_attempts:
                    failures.append(f"{label}: invalid/duplicate saved episode index {saved_index!r}")
                else:
                    saved_attempts[saved_index] = (folder_session, attempt_id, frames)
                if saved_index != candidate:
                    failures.append(f"{label}: saved episode index differs from candidate")
                if isinstance(saved_index, int):
                    session_saved_indices.append(saved_index)
            elif saved_index is not None:
                failures.append(f"{label}: discarded attempt carries a saved episode index")
            reason = end_row.get("reason")
            _validate_episode_end_semantics(end_row, label, failures)
            if reason == "accept":
                reason_counts["accepted"] += 1
            elif reason == "timeout":
                reason_counts["timed_out"] += 1
            elif reason == "discard":
                reason_counts["discarded"] += 1
            elif reason == "stop_interrupted":
                reason_counts["interrupted"] += 1
            attempt_summaries.append(
                {
                    "attempt_id": attempt_id,
                    "saved": saved,
                    "saved_episode_index": saved_index,
                    "reason": reason,
                    "frames": len(frames),
                    "loop_hz_mean": 1.0 / statistics.mean(intervals) if intervals else None,
                    "camera_update_rates": {
                        camera: _rate_summary(stamps) for camera, stamps in sorted(camera_stamps.items())
                    },
                }
            )
        expected_indices = list(
            range(expected_existing_episodes, expected_existing_episodes + len(session_saved_indices))
        )
        if sorted(session_saved_indices) != expected_indices:
            failures.append(
                f"session {folder_session}: saved indices {sorted(session_saved_indices)} "
                f"!= contiguous append {expected_indices}"
            )
        counters = ends[0].get("counters")
        counter_keys = {"attempted", "saved", "accepted", "timed_out", "discarded", "interrupted"}
        if not isinstance(counters, dict) or set(counters) != counter_keys:
            failures.append(f"session {folder_session}: session_end counters are incomplete or unexpected")
        else:
            expected_counters = {
                "attempted": len(attempts),
                "saved": len(session_saved_indices),
                **reason_counts,
            }
            if counters != expected_counters:
                failures.append(
                    f"session {folder_session}: counters {counters} != observed {expected_counters}"
                )
        if ends[0].get("end_reason") == "completed" and additional_requested != len(session_saved_indices):
            failures.append(
                f"session {folder_session}: completed session saved {len(session_saved_indices)} "
                f"!= requested {additional_requested}"
            )
        expected_existing_episodes += len(session_saved_indices)
        session_summaries.append(
            {
                "session_id": folder_session,
                "existing_episodes": existing,
                "additional_episodes_requested": additional_requested,
                "attempts": attempt_summaries,
            }
        )

    if set(saved_attempts) != set(parquet_by_episode):
        failures.append(
            f"saved sidecar episodes {sorted(saved_attempts)} != Parquet episodes {sorted(parquet_by_episode)}"
        )
    if expected_existing_episodes != len(parquet_by_episode):
        failures.append(
            f"sidecar session topology ends at {expected_existing_episodes} episodes but Parquet has "
            f"{len(parquet_by_episode)}"
        )
    for episode_index, parquet_rows in parquet_by_episode.items():
        mapping = saved_attempts.get(episode_index)
        if mapping is None:
            continue
        session_id, attempt_id, frames = mapping
        if len(frames) != len(parquet_rows):
            failures.append(
                f"session {session_id} attempt {attempt_id}: sidecar frames {len(frames)} "
                f"!= episode {episode_index} Parquet frames {len(parquet_rows)}"
            )
            continue
        for frame_index, (trace_row, parquet_row) in enumerate(zip(frames, parquet_rows, strict=True)):
            action = _finite_vector(trace_row.get("requested_processed_official_action"))
            state = _finite_vector(trace_row.get("measured_state_pre_command"))
            parquet_action = _finite_vector(parquet_row.get("action"))
            parquet_state = _finite_vector(parquet_row.get("observation.state"))
            if action is None or parquet_action is None or not np.allclose(action, parquet_action, rtol=0, atol=1e-6):
                failures.append(f"episode {episode_index} frame {frame_index}: official action trace != Parquet action")
            if state is None or parquet_state is None or not np.allclose(state, parquet_state, rtol=0, atol=1e-6):
                failures.append(f"episode {episode_index} frame {frame_index}: measured state trace != Parquet state")

    return {
        "sessions": session_summaries,
        "saved_episode_mapping": {
            str(index): {"session_id": value[0], "attempt_id": value[1]}
            for index, value in sorted(saved_attempts.items())
        },
        "time_semantics": "per-session/per-attempt host monotonic timing; Dataset timestamp is frame_index/fps",
    }


def _early_failure(repo_id: str, dataset_dir: Path | None, failure: str) -> dict[str, Any]:
    """Return a stable audit result when input cannot be inspected safely."""

    return {
        "status": "FAIL",
        "repo_id": repo_id,
        "dataset_dir": str(dataset_dir) if dataset_dir is not None else None,
        "dataset_fps": None,
        "episodes": None,
        "frames": None,
        "cameras": [],
        "joint_units": {
            **{name: "degree" for name in EXPECTED_JOINT_NAMES[:5]},
            "gripper.pos": "normalized_0_100",
        },
        "action_semantics": "processed_operator_target",
        "timestamp_semantics": "nominal_frame_index_div_dataset_fps",
        "failures": [failure],
        "videos": {},
        "sidecar": {},
        "profile_path": str(_profile_path(repo_id)),
        "read_only_manifest_unchanged": None,
    }


def audit(repo_id: str, expected_cameras: list[str]) -> dict[str, Any]:
    failures: list[str] = []
    dataset_dir: Path | None = None
    try:
        dataset_dir = resolve_dataset_dir(repo_id)
        # The manifest walk rejects every linked/special descendant before any
        # Parquet or media decoder sees project-external bytes.
        before = _manifest(dataset_dir)
        info = read_info(dataset_dir)
        episodes = read_episode_index(dataset_dir)
        cameras = list_cameras(dataset_dir)
    except Exception as exc:  # noqa: BLE001 - malformed/untrusted local dataset input
        return _early_failure(repo_id, dataset_dir, f"unable to inspect dataset safely: {exc}")

    metadata_values: dict[str, int] = {}
    for key in ("total_episodes", "total_frames", "fps"):
        value = info.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            failures.append(f"Dataset metadata {key} must be an integer")
            metadata_values[key] = 0
        else:
            metadata_values[key] = value
    declared_episodes = metadata_values["total_episodes"]
    declared_frames = metadata_values["total_frames"]
    fps = metadata_values["fps"]
    if declared_episodes < 1:
        failures.append("Dataset must contain at least one episode")
    if declared_frames < 1:
        failures.append("Dataset must contain at least one frame")
    if declared_episodes != len(episodes):
        failures.append(f"declared episodes {declared_episodes} != indexed episodes {len(episodes)}")
    indices = [row.episode_idx for row in episodes]
    if indices != list(range(declared_episodes)):
        failures.append(f"episode indices are not contiguous: {indices}")
    if sum(row.length for row in episodes) != declared_frames:
        failures.append("sum of episode lengths differs from declared total_frames")
    if sorted(cameras) != sorted(expected_cameras):
        failures.append(f"camera keys {cameras} != expected {expected_cameras}")
    if fps <= 0:
        failures.append("Dataset fps must be positive")

    action_names = _feature_names(info, "action")
    state_names = _feature_names(info, "observation.state")
    if action_names != EXPECTED_JOINT_NAMES:
        failures.append(f"action names {action_names} != expected SO-101 order")
    if state_names != EXPECTED_JOINT_NAMES:
        failures.append(f"state names {state_names} != expected SO-101 order")

    profile = _load_profile(repo_id, failures)
    _validate_profile(profile, info, expected_cameras, failures)

    try:
        parquet_rows, _available_columns, common_columns = _read_parquet_rows(dataset_dir)
    except Exception as exc:  # noqa: BLE001 - report malformed input instead of aborting the audit
        failures.append(f"unable to read Parquet data: {exc}")
        parquet_rows, _available_columns, common_columns = [], set(), set()
    missing_columns = sorted(REQUIRED_PARQUET_COLUMNS - common_columns)
    if missing_columns:
        failures.append(f"Parquet columns missing from one or more files: {missing_columns}")
    if len(parquet_rows) != declared_frames:
        failures.append(f"Parquet rows {len(parquet_rows)} != declared_frames {declared_frames}")

    parquet_by_episode = _parse_parquet_rows(
        parquet_rows,
        fps=fps,
        declared_frames=declared_frames,
        failures=failures,
    )

    indexed_by_episode = {row.episode_idx: row for row in episodes}
    task = (profile or {}).get("single_task")
    for episode_index, rows in sorted(parquet_by_episode.items()):
        rows.sort(key=lambda row: row["frame_index"])
        index_row = indexed_by_episode.get(episode_index)
        if index_row is None:
            failures.append(f"Parquet episode {episode_index} is absent from episode metadata")
            continue
        if [row["frame_index"] for row in rows] != list(range(index_row.length)):
            failures.append(f"episode {episode_index}: frame_index is not contiguous or length differs")
        if task is not None and list(index_row.tasks) != [task]:
            failures.append(f"episode {episode_index}: task labels {list(index_row.tasks)} != frozen task")
        task_indices = {row["task_index"] for row in rows}
        if len(task_indices) != 1:
            failures.append(f"episode {episode_index}: multiple task_index values {sorted(task_indices)}")

    videos: dict[str, Any] = {}
    profile_cameras = (profile or {}).get("cameras") or {}
    for episode in episodes:
        episode_videos: dict[str, Any] = {}
        for camera in expected_cameras:
            try:
                summary = _video_window_summary(dataset_dir, episode.episode_idx, camera)
                episode_videos[camera] = summary
                if summary["codec"] not in {"h264", "libx264"}:
                    failures.append(f"episode {episode.episode_idx} camera {camera}: codec={summary['codec']}")
                if summary["pixel_format"] != "yuv420p":
                    failures.append(
                        f"episode {episode.episode_idx} camera {camera}: pixel_format={summary['pixel_format']}"
                    )
                if not summary["pts_monotonic"]:
                    failures.append(f"episode {episode.episode_idx} camera {camera}: non-monotonic PTS")
                if summary["decoded_frames"] != episode.length:
                    failures.append(
                        f"episode {episode.episode_idx} camera {camera}: decoded "
                        f"{summary['decoded_frames']} != Parquet length {episode.length}"
                    )
                camera_profile = profile_cameras.get(camera) or {}
                if (
                    summary["width"] != camera_profile.get("width")
                    or summary["height"] != camera_profile.get("height")
                ):
                    failures.append(f"episode {episode.episode_idx} camera {camera}: dimensions differ from profile")
                if summary["average_rate"] is not None and not math.isclose(
                    summary["average_rate"], fps, rel_tol=0.0, abs_tol=1e-6
                ):
                    failures.append(f"episode {episode.episode_idx} camera {camera}: encoded FPS differs from Dataset FPS")
            except Exception as exc:  # noqa: BLE001 - continue auditing every camera
                failures.append(f"episode {episode.episode_idx} camera {camera}: {exc}")
        videos[str(episode.episode_idx)] = episode_videos

    sidecar = _sidecar_summary(repo_id, profile, expected_cameras, parquet_by_episode, failures)

    try:
        after = _manifest(dataset_dir)
    except UnsafeDatasetPathError as exc:
        after = {}
        failures.append(f"dataset became unsafe during read-only audit: {exc}")
    if after != before:
        failures.append("dataset changed during read-only audit")

    return {
        "status": "FAIL" if failures else "PASS",
        "repo_id": repo_id,
        "dataset_dir": str(dataset_dir),
        "dataset_fps": info.get("fps"),
        "episodes": declared_episodes,
        "frames": declared_frames,
        "cameras": cameras,
        "joint_units": {
            **{name: "degree" for name in EXPECTED_JOINT_NAMES[:5]},
            "gripper.pos": "normalized_0_100",
        },
        "action_semantics": "processed_operator_target",
        "timestamp_semantics": "nominal_frame_index_div_dataset_fps",
        "failures": failures,
        "videos": videos,
        "sidecar": sidecar,
        "profile_path": str(_profile_path(repo_id)),
        "read_only_manifest_unchanged": after == before,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo_id")
    parser.add_argument("--camera", action="append", dest="cameras", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.repo_id, args.cameras or ["arm", "table_veiw"])
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        evidence_root = _evidence_root()
        target = args.output.expanduser().resolve()
        if target == evidence_root or evidence_root not in target.parents:
            raise SystemExit("--output must stay inside LELAB_RECORDING_EVIDENCE_ROOT")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered + "\n", encoding="utf-8")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
