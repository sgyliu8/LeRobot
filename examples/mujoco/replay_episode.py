"""Drive the pinned SO101 MuJoCo model from one recorded Dataset v3 episode."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import secrets
import subprocess
import time
from pathlib import Path

# This experiment is an offline reader. Missing local files are an error, not
# a reason to repair a dataset from the Hub.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_DATASETS_OFFLINE"] = "1"

import mujoco
import numpy as np
from lerobot.datasets.lerobot_dataset import LeRobotDataset

JOINT_NAMES = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)
DATASET_JOINT_NAMES = tuple(f"{name}.pos" for name in JOINT_NAMES)
MENAGERIE_COMMIT = "8161bba264d7fa7c99ca301e91e7fb44737676ad"
MENAGERIE_ORIGIN = "https://github.com/google-deepmind/mujoco_menagerie.git"
EXPECTED_UNITS = {
    **{name: "degree" for name in JOINT_NAMES[:-1]},
    "gripper": "normalized_0_100",
}
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--dataset-root", type=Path)
    parser.add_argument(
        "--profile",
        type=Path,
        required=True,
        help="Frozen local recording profile that establishes joint units and action semantics",
    )
    parser.add_argument("--episode", type=int, default=0)
    parser.add_argument(
        "--model",
        type=Path,
        default=PROJECT_ROOT / ".local/upstream/mujoco_menagerie/robotstudio_so101/scene.xml",
    )
    parser.add_argument("--viewer", action="store_true")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--clip", action="store_true", help="Explicitly clip values outside MJCF ranges")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--trajectory-jsonl", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def _local_dataset_root(repo_id: str, explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve(strict=True)
    parts = Path(repo_id).parts
    if not parts or Path(repo_id).is_absolute() or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("dataset-id must be a relative local repository id")
    if os.environ.get("HF_LEROBOT_HOME"):
        base = Path(os.environ["HF_LEROBOT_HOME"])
    elif os.environ.get("HF_HOME"):
        base = Path(os.environ["HF_HOME"]) / "lerobot"
    else:
        base = Path.home() / ".cache" / "huggingface" / "lerobot"
    return base.joinpath(*parts).resolve(strict=True)


def _load_profile(path: Path, dataset_id: str) -> tuple[dict[str, str], str, int, str]:
    profile_path = path.expanduser().resolve(strict=True)
    payload = profile_path.read_bytes()
    profile = json.loads(payload)
    if not isinstance(profile, dict):
        raise TypeError("recording profile must be a JSON object")
    if profile.get("dataset_repo_id") != dataset_id:
        raise ValueError("recording profile dataset_repo_id does not match --dataset-id")
    units = profile.get("max_relative_target_units")
    if units != EXPECTED_UNITS:
        raise ValueError(f"recording profile must declare exact units {EXPECTED_UNITS!r}")
    action_semantics = profile.get("action_semantics")
    if action_semantics != "processed_operator_target":
        raise ValueError("recording profile action_semantics must be processed_operator_target")
    nominal_fps = profile.get("dataset_fps")
    if not isinstance(nominal_fps, int) or nominal_fps <= 0:
        raise ValueError("recording profile dataset_fps must be a positive integer")
    return dict(units), action_semantics, nominal_fps, hashlib.sha256(payload).hexdigest()


def _prepare_output(
    path: Path | None,
    dataset_root: Path,
    overwrite: bool,
    project_root: Path = PROJECT_ROOT,
) -> Path | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    if resolved == dataset_root or dataset_root in resolved.parents:
        raise ValueError("derived output must not be written inside the source dataset")
    local_root = (project_root.resolve() / ".local").resolve()
    if resolved != local_root and local_root not in resolved.parents:
        raise ValueError("derived playback outputs must stay under the project .local directory")
    if resolved.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing output: {resolved}")
    return resolved


def _write_atomic(path: Path, payload: str, overwrite: bool) -> None:
    """Publish a complete derived file without exposing a partial target."""
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
            # A same-directory hard link atomically fails if another process
            # created the requested output after _prepare_output checked it.
            os.link(temporary, path)
            temporary.unlink()
    finally:
        temporary.unlink(missing_ok=True)


def _verify_menagerie_source(model_path: Path) -> dict[str, str]:
    expected_relative = Path("robotstudio_so101") / "scene.xml"
    repository = model_path.parents[1]
    if model_path != repository / expected_relative:
        raise ValueError("--model must be the pinned Menagerie robotstudio_so101/scene.xml")

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    origin = git("remote", "get-url", "origin")
    head = git("rev-parse", "HEAD")
    dirty = git("status", "--porcelain")
    if origin != MENAGERIE_ORIGIN or head != MENAGERIE_COMMIT or dirty:
        raise ValueError("MuJoCo model checkout is not the clean pinned Menagerie source")
    return {"origin": origin, "commit": head}


def _joint_names(dataset: LeRobotDataset, feature: str) -> list[str]:
    names = dataset.meta.features.get(feature, {}).get("names")
    if not isinstance(names, list) or names != list(DATASET_JOINT_NAMES):
        raise ValueError(
            f"{feature} names must be exactly {list(DATASET_JOINT_NAMES)!r}; got {names!r}"
        )
    return names


def _to_model_qpos(values: np.ndarray) -> np.ndarray:
    if values.shape != (6,) or not np.isfinite(values).all():
        raise ValueError(f"Expected six finite joint values, got {values!r}")
    # SO101 Dataset v3 records the five arm joints in degrees. The gripper is
    # normalized 0..100, not a metric opening; matching LeLab's visualizer, it
    # is mapped to the same numeric degree sweep solely for visual playback.
    return np.deg2rad(values.astype(np.float64))


def _load_experiment_model(model_path: Path) -> mujoco.MjModel:
    spec = mujoco.MjSpec.from_file(str(model_path))
    table = spec.worldbody.add_body(name="experiment_table", pos=[0.3, 0.0, 0.08])
    table.add_geom(
        name="experiment_table_top",
        type=mujoco.mjtGeom.mjGEOM_BOX,
        size=[0.25, 0.30, 0.08],
        rgba=[0.45, 0.32, 0.20, 1.0],
    )
    block = spec.worldbody.add_body(name="experiment_block", pos=[0.25, 0.0, 0.19])
    block.add_geom(
        name="experiment_block_geom",
        type=mujoco.mjtGeom.mjGEOM_BOX,
        size=[0.03, 0.03, 0.03],
        rgba=[0.80, 0.10, 0.10, 1.0],
    )
    return spec.compile()


def replay(args: argparse.Namespace) -> dict[str, object]:
    if args.episode < 0:
        raise ValueError("episode must be non-negative")
    if not math.isfinite(args.speed) or args.speed <= 0:
        raise ValueError("speed must be a positive finite number")
    model_path = args.model.resolve(strict=True)
    provenance = _verify_menagerie_source(model_path)
    dataset_root = _local_dataset_root(args.dataset_id, args.dataset_root)
    profile_units, action_semantics, profile_fps, profile_sha256 = _load_profile(
        args.profile, args.dataset_id
    )
    report_path = _prepare_output(args.report, dataset_root, args.overwrite)
    trajectory_path = _prepare_output(args.trajectory_jsonl, dataset_root, args.overwrite)
    if report_path is not None and report_path == trajectory_path:
        raise ValueError("report and trajectory-jsonl must be different files")
    for required in (dataset_root / "meta" / "info.json", dataset_root / "data"):
        if not required.exists():
            raise FileNotFoundError(f"Local Dataset v3 artifact is missing: {required}")

    dataset = LeRobotDataset(
        repo_id=args.dataset_id,
        root=dataset_root,
        episodes=[args.episode],
        video_backend="pyav",
        download_videos=False,
    )
    _joint_names(dataset, "observation.state")
    _joint_names(dataset, "action")
    columns = dataset.select_columns(
        ["episode_index", "frame_index", "timestamp", "observation.state", "action"]
    )
    if len(columns) == 0:
        raise ValueError(f"Episode {args.episode} contains no frames")

    episode_indices = np.asarray(columns["episode_index"], dtype=np.int64)
    if not np.all(episode_indices == args.episode):
        raise ValueError("Official episode filter returned rows from another episode")
    frame_indices = np.asarray(columns["frame_index"], dtype=np.int64)
    timestamps = np.asarray(columns["timestamp"], dtype=np.float64)
    observations = np.asarray(columns["observation.state"], dtype=np.float64)
    actions = np.asarray(columns["action"], dtype=np.float64)
    if observations.shape != (len(columns), 6) or actions.shape != observations.shape:
        raise ValueError("Dataset action/state shape is not N x 6")
    if not np.isfinite(observations).all() or not np.isfinite(actions).all():
        raise ValueError("Episode state and action values must be finite")
    if not np.array_equal(frame_indices, np.arange(len(columns), dtype=np.int64)):
        raise ValueError("Episode frame_index must be contiguous from zero")
    if (
        not np.isfinite(timestamps).all()
        or abs(float(timestamps[0])) > 1e-9
        or np.any(np.diff(timestamps) <= 0)
    ):
        raise ValueError("Episode timestamps must start at zero and be strictly increasing")
    if dataset.fps != profile_fps:
        raise ValueError("recording profile Dataset FPS does not match Dataset v3 metadata")
    nominal_timestamps = frame_indices.astype(np.float64) / float(dataset.fps)
    max_nominal_timestamp_error = float(np.max(np.abs(timestamps - nominal_timestamps)))
    if max_nominal_timestamp_error > 1e-4:
        raise ValueError("Episode timestamps do not match the Dataset nominal frame timeline")

    model = _load_experiment_model(model_path)
    data = mujoco.MjData(model)
    joint_ids = []
    for name in JOINT_NAMES:
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if joint_id < 0:
            raise ValueError(f"MJCF is missing joint {name!r}")
        joint_ids.append(joint_id)
    if len(set(joint_ids)) != len(JOINT_NAMES) or model.njnt != len(JOINT_NAMES):
        raise ValueError("Pinned MJCF must expose exactly six distinct joints")
    for name, joint_id in zip(JOINT_NAMES, joint_ids):
        if model.jnt_type[joint_id] != mujoco.mjtJoint.mjJNT_HINGE or not model.jnt_limited[joint_id]:
            raise ValueError(f"MJCF joint {name!r} must be a limited scalar hinge")
    qpos_addresses = np.asarray([model.jnt_qposadr[joint_id] for joint_id in joint_ids], dtype=np.int64)
    if len(set(qpos_addresses.tolist())) != len(JOINT_NAMES):
        raise ValueError("Pinned MJCF joint qpos addresses are not unique")
    limits = np.asarray([model.jnt_range[joint_id] for joint_id in joint_ids], dtype=np.float64)
    qpos_frames = np.vstack([_to_model_qpos(row) for row in observations])
    range_epsilon = 1e-6
    below = qpos_frames < limits[:, 0] - range_epsilon
    above = qpos_frames > limits[:, 1] + range_epsilon
    violation_counts = (below | above).sum(axis=0)
    if violation_counts.any() and not args.clip:
        details = {name: int(count) for name, count in zip(JOINT_NAMES, violation_counts) if count}
        raise ValueError(f"Episode exceeds pinned MJCF joint ranges: {details}. Use --clip explicitly.")
    boundary_adjustments = (
        ((qpos_frames < limits[:, 0]) | (qpos_frames > limits[:, 1])) & ~(below | above)
    ).sum(axis=0)
    effective_frames = (
        np.clip(qpos_frames, limits[:, 0], limits[:, 1])
        if args.clip or boundary_adjustments.any()
        else qpos_frames
    )

    source_digest = hashlib.sha256()
    source_digest.update(frame_indices.tobytes())
    source_digest.update(timestamps.tobytes())
    source_digest.update(observations.tobytes())
    source_digest.update(actions.tobytes())
    source_episode_arrays_sha256 = source_digest.hexdigest()

    range_violation_counts = {
        name: int(count) for name, count in zip(JOINT_NAMES, violation_counts)
    }
    boundary_adjustment_counts = {
        name: int(count) for name, count in zip(JOINT_NAMES, boundary_adjustments)
    }
    trajectory_file_sha256: str | None = None
    if trajectory_path:
        transform = {
            "kind": "dataset_state_to_model_radians",
            "arm": "degree_to_radian",
            "gripper": "normalized_0_100_as_numeric_degrees_to_radians_visual_only",
            "mjcf_range_clip_enabled": bool(args.clip),
            "mjcf_range_violation_counts": range_violation_counts,
            "mjcf_boundary_adjustment_counts": boundary_adjustment_counts,
        }
        rows = []
        for index, (timestamp, positions) in enumerate(zip(timestamps, effective_frames)):
            rows.append(
                json.dumps(
                    {
                        "schema_version": 2,
                        "dataset_id": args.dataset_id,
                        "episode": args.episode,
                        "frame_index": index,
                        "expected_frames": len(columns),
                        "source_episode_arrays_sha256": source_episode_arrays_sha256,
                        "timestamp": float(timestamp - timestamps[0]),
                        "source_feature_names": list(DATASET_JOINT_NAMES),
                        "source_units": [profile_units[name] for name in JOINT_NAMES],
                        "model_joint_names": list(JOINT_NAMES),
                        "positions_rad": positions.astype(float).tolist(),
                        "transform": transform,
                    },
                    separators=(",", ":"),
                )
            )
        _write_atomic(trajectory_path, "\n".join(rows) + "\n", args.overwrite)
        trajectory_file_sha256 = hashlib.sha256(trajectory_path.read_bytes()).hexdigest()

    end_site = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "gripperframe")
    if end_site < 0:
        raise ValueError("Pinned MJCF is missing the gripperframe reference site")
    first_ee: list[float] | None = None
    last_ee: list[float] | None = None

    def apply_frame(index: int) -> None:
        nonlocal first_ee, last_ee
        data.qpos[qpos_addresses] = effective_frames[index]
        mujoco.mj_forward(model, data)
        position = data.site_xpos[end_site].astype(float).tolist()
        if index == 0:
            first_ee = position
        if index == len(effective_frames) - 1:
            last_ee = position

    if args.viewer:
        from mujoco import viewer as mujoco_viewer

        with mujoco_viewer.launch_passive(model, data) as viewer:
            previous = float(timestamps[0])
            for index, timestamp in enumerate(timestamps):
                apply_frame(index)
                viewer.sync()
                delay = max(0.0, float(timestamp) - previous) / args.speed
                previous = float(timestamp)
                if delay:
                    time.sleep(delay)
    else:
        for index in range(len(effective_frames)):
            apply_frame(index)

    report: dict[str, object] = {
        "status": "PASS",
        "mode": "kinematic_viewer" if args.viewer else "kinematic_headless",
        "menagerie_origin": provenance["origin"],
        "menagerie_commit": provenance["commit"],
        "model_path": str(model_path),
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "mujoco_version": mujoco.__version__,
        "scene_objects": ["experiment_table", "experiment_block"],
        "dataset_id": args.dataset_id,
        "episode": args.episode,
        "frames": len(columns),
        "nominal_fps": dataset.fps,
        "nominal_duration_s": float(timestamps[-1] - timestamps[0]),
        "max_nominal_timestamp_error_s": max_nominal_timestamp_error,
        "source_episode_arrays_sha256": source_episode_arrays_sha256,
        "trajectory_file_sha256": trajectory_file_sha256,
        "trajectory_jsonl": str(trajectory_path) if trajectory_path else None,
        "source": "observation.state (pre-command measured state)",
        "source_feature_names": list(DATASET_JOINT_NAMES),
        "source_units": profile_units,
        "profile_sha256": profile_sha256,
        "action_semantics": f"recorded {action_semantics}; loaded and finite-checked but not applied",
        "gripper_mapping": "normalized_0_100 mapped as numeric degrees to radians; visual-only",
        "clip_enabled": bool(args.clip),
        "range_violation_counts": range_violation_counts,
        "boundary_adjustment_counts": boundary_adjustment_counts,
        "joint_ranges_rad": {
            name: limits[index].astype(float).tolist() for index, name in enumerate(JOINT_NAMES)
        },
        "first_qpos_rad": effective_frames[0].astype(float).tolist(),
        "last_qpos_rad": effective_frames[-1].astype(float).tolist(),
        "end_effector_site": "gripperframe",
        "first_end_effector_xyz_m": first_ee,
        "last_end_effector_xyz_m": last_ee,
        "viewer_event_loop": "PASS" if args.viewer else "NOT_RUN",
        "visual_inspection": "NOT_RUN",
        "physical_registration": (
            "NOT_RUN: joint zero/sign conventions are inherited from the fixed Dataset and "
            "Menagerie sources and were not registered against the physical arm"
        ),
        "claim_boundary": (
            "Recorded states drove a pinned model through forward kinematics only; "
            "this is not dynamics, collision safety, task success, physical registration, "
            "or real-robot evidence."
        ),
    }
    return report


def main() -> int:
    args = _parser().parse_args()
    report = replay(args)
    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.report:
        report_path = args.report.expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(report_path, rendered + "\n", args.overwrite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
