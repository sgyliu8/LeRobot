from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from so101_lab.color_sorting import (
    AttemptLabel,
    ColorSortingProfile,
    append_attempt_label,
    build_split_manifest,
    load_attempt_labels,
    load_profile,
    local_labels_path,
    local_split_manifest_path,
    local_summary_path,
    observe_frame,
    profile_fingerprint,
    summarize_attempts,
    validate_split_manifest,
    write_local_split_manifest,
    write_local_summary,
)
from so101_lab.color_sorting_cli import main as color_sorting_main


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_PROFILE = ROOT / "configs" / "tasks" / "color_sorting.example.json"


def _configured_profile() -> ColorSortingProfile:
    payload = json.loads(PUBLIC_PROFILE.read_text(encoding="utf-8"))
    payload["stage"] = "C1"
    payload["dataset"]["repo_id"] = "local/color_sorting_v1_fixture"
    payload["entities"]["cube_size_mm"] = [30.0, 30.0, 30.0]
    ranges = {
        "color_a": [
            {"lower": [0, 150, 100], "upper": [10, 255, 255]},
            {"lower": [170, 150, 100], "upper": [179, 255, 255]},
        ],
        "color_b": [{"lower": [45, 120, 80], "upper": [85, 255, 255]}],
        "color_c": [{"lower": [100, 120, 80], "upper": [130, 255, 255]}],
    }
    names = {"color_a": "red", "color_b": "green", "color_c": "blue"}
    for color in payload["entities"]["colors"]:
        color["display_name"] = names[color["id"]]
        color["hsv_ranges"] = ranges[color["id"]]
        color["instance_ids"] = [f"{color['id']}_cube_01"]
    for bin_spec in payload["entities"]["bins"]:
        bin_spec["opening_size_mm"] = [80.0, 80.0, 50.0]
    payload["scene"]["source_roi"] = {"x": 0.05, "y": 0.1, "width": 0.4, "height": 0.8}
    payload["scene"]["layout_id"] = "layout-fixed-v1"
    payload["scene"]["gripper_exclusion_rois"] = [
        {"x": 0.05, "y": 0.1, "width": 0.2, "height": 0.15}
    ]
    bin_rois = {
        "color_a": ({"x": 0.55, "y": 0.05, "width": 0.12, "height": 0.3}, {"x": 0.53, "y": 0.03, "width": 0.16, "height": 0.34}),
        "color_b": ({"x": 0.7, "y": 0.35, "width": 0.12, "height": 0.3}, {"x": 0.68, "y": 0.33, "width": 0.16, "height": 0.34}),
        "color_c": ({"x": 0.84, "y": 0.65, "width": 0.12, "height": 0.3}, {"x": 0.82, "y": 0.63, "width": 0.16, "height": 0.34}),
    }
    for region in payload["scene"]["bin_regions"]:
        interior, rim = bin_rois[region["color_id"]]
        region["interior_roi"] = interior
        region["rim_roi"] = rim
    payload["recording_profile_id"] = "fixture-profile-sha256"
    payload["calibration_id"] = "fixture-calibration"
    payload["project_commit"] = "a" * 40
    return ColorSortingProfile.model_validate(payload)


def _observe(frame: np.ndarray, profile: ColorSortingProfile, **kwargs):
    return observe_frame(
        frame,
        profile,
        camera_key="table_veiw",
        frame_id="fixture-0001",
        captured_at_s=10.0,
        now_s=10.1,
        **kwargs,
    )


def test_public_profile_is_explicitly_unconfigured_and_preserves_contract() -> None:
    profile = load_profile(PUBLIC_PROFILE)

    assert profile.task_id == "color_sorting_v1"
    assert profile.dataset.camera_aliases == {"arm": "wrist", "table_veiw": "front"}
    assert profile.policy.type == "act"
    assert profile.policy.chunk_size == 32
    assert profile.policy.n_action_steps == 8
    assert profile.policy.task_text_consumed is False
    issues = profile.capture_readiness_issues()
    assert "task stage is C0; select an attended capture stage" in issues
    assert "dataset.repo_id is not frozen" in issues
    assert any("actual color" in issue for issue in issues)
    assert any("source ROI" in issue for issue in issues)


def test_observer_handles_rgb_and_bgr_without_opening_a_camera(monkeypatch) -> None:
    profile = _configured_profile()
    assert profile.capture_readiness_issues() == []
    bgr = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(bgr, (45, 70), (75, 100), (0, 0, 255), -1)

    monkeypatch.setattr(cv2, "VideoCapture", lambda *_a, **_k: pytest.fail("camera was opened"))
    from_bgr = _observe(bgr, profile, color_order="BGR")
    from_rgb = _observe(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), profile, color_order="RGB")

    assert from_bgr.status == "valid"
    assert [(d.color_id, d.region) for d in from_bgr.detections] == [("color_a", "source")]
    assert from_rgb.detections == from_bgr.detections


def test_observer_enforces_camera_owner_object_count_and_exclusion_rois() -> None:
    profile = _configured_profile()
    frame = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(frame, (45, 70), (75, 100), (0, 0, 255), -1)
    cv2.rectangle(frame, (90, 120), (120, 150), (0, 255, 0), -1)

    wrong_camera = observe_frame(
        frame,
        profile,
        camera_key="arm",
        frame_id="fixture-wrist",
        captured_at_s=10.0,
        now_s=10.1,
    )
    assert wrong_camera.status == "unknown"
    assert wrong_camera.issues == ["camera_role_not_configured"]

    too_many = _observe(frame, profile)
    assert too_many.status == "unknown"
    assert "unexpected_object_count" in too_many.issues

    excluded = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(excluded, (45, 25), (70, 45), (0, 0, 255), -1)
    excluded_result = _observe(excluded, profile)
    assert excluded_result.detections == []
    assert excluded_result.status == "unknown"
    assert "unexpected_object_count" in excluded_result.issues

    partial = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(partial, (65, 25), (90, 45), (0, 0, 255), -1)
    partial_result = _observe(partial, profile)
    assert partial_result.status == "unknown"
    assert "occluded_or_outside_roi" in partial_result.issues


def test_bin_rim_is_not_a_cube_and_same_color_bin_needs_human_verification() -> None:
    profile = _configured_profile()
    frame = np.zeros((200, 300, 3), dtype=np.uint8)
    # Red in the rim-only area is excluded from cube search.
    cv2.rectangle(frame, (160, 6), (166, 64), (0, 0, 255), -1)
    assert _observe(frame, profile).detections == []

    # A red component inside the red bin remains ambiguous because the bin has
    # a same-color interior; it is not promoted to task success.
    cv2.rectangle(frame, (170, 20), (190, 40), (0, 0, 255), -1)
    observed = _observe(frame, profile)
    red_bin = next(d for d in observed.detections if d.region == "bin:color_a")
    assert red_bin.validity == "unknown"
    assert "manual_verification_required" in observed.issues


def test_observer_returns_unknown_for_stale_bad_occluded_and_unclassified_frames() -> None:
    profile = _configured_profile()
    blank = np.zeros((200, 300, 3), dtype=np.uint8)

    stale = observe_frame(
        blank,
        profile,
        camera_key="table_veiw",
        frame_id="stale",
        captured_at_s=1.0,
        now_s=5.0,
        color_order="BGR",
    )
    assert stale.status == "unknown"
    assert stale.issues == ["stale_frame"]

    invalid_time = observe_frame(
        blank,
        profile,
        camera_key="table_veiw",
        frame_id="future",
        captured_at_s=2.0,
        now_s=1.0,
        color_order="BGR",
    )
    assert invalid_time.issues == ["invalid_frame_timestamp"]

    bad = _observe(np.empty((0, 0, 3), dtype=np.uint8), profile, color_order="BGR")
    assert bad.status == "unknown"
    assert bad.issues == ["invalid_frame"]

    unknown = blank.copy()
    cv2.rectangle(unknown, (45, 70), (75, 100), (0, 255, 255), -1)
    unknown_result = _observe(unknown, profile, color_order="BGR")
    assert unknown_result.status == "unknown"
    assert "unknown_color" in unknown_result.issues

    occluded = blank.copy()
    cv2.rectangle(occluded, (15, 50), (40, 90), (0, 0, 255), -1)
    occluded_result = _observe(occluded, profile, color_order="BGR")
    assert occluded_result.status == "unknown"
    assert "occluded_or_outside_roi" in occluded_result.issues


def test_profile_rejects_ambiguous_hsv_and_noncanonical_dataset_identity() -> None:
    profile = _configured_profile().model_dump(mode="json")
    profile["entities"]["colors"][1]["hsv_ranges"] = [
        {"lower": [5, 160, 110], "upper": [15, 250, 250]}
    ]
    with pytest.raises(ValueError, match="HSV ranges overlap"):
        ColorSortingProfile.model_validate(profile)

    profile = _configured_profile().model_dump(mode="json")
    profile["dataset"]["repo_id"] = "missing-namespace"
    with pytest.raises(ValueError, match="exact '<namespace>/<name>'"):
        ColorSortingProfile.model_validate(profile)

    profile = _configured_profile().model_dump(mode="json")
    profile["dataset"]["repo_id"] = "../escape"
    with pytest.raises(ValueError, match="exact '<namespace>/<name>'"):
        ColorSortingProfile.model_validate(profile)

    profile = _configured_profile().model_dump(mode="json")
    profile["project_commit"] = "short"
    with pytest.raises(ValueError, match="full lowercase Git commit"):
        ColorSortingProfile.model_validate(profile)

    profile = _configured_profile().model_dump(mode="json")
    profile["scene"]["source_roi"] = profile["scene"]["bin_regions"][0]["interior_roi"]
    with pytest.raises(ValueError, match="task ROIs overlap"):
        ColorSortingProfile.model_validate(profile)

    profile = _configured_profile().model_dump(mode="json")
    profile["entities"]["cube_size_mm"][0] = float("nan")
    with pytest.raises(ValueError, match="cube dimensions must be finite and positive"):
        ColorSortingProfile.model_validate(profile)

    profile = _configured_profile().model_dump(mode="json")
    profile["policy"]["chunk_size"] = True
    profile["policy"]["n_action_steps"] = True
    with pytest.raises(ValueError):
        ColorSortingProfile.model_validate(profile)

    profile = _configured_profile().model_dump(mode="json")
    profile["recording_profile_id"] = " "
    with pytest.raises(ValueError, match="non-empty and trimmed"):
        ColorSortingProfile.model_validate(profile)


def _label(**overrides) -> AttemptLabel:
    payload = {
        "dataset_repo_id": "local/color_sorting_v1_fixture",
        "session_id": "session-a",
        "scene_id": "scene-1",
        "layout_id": "layout-fixed-v1",
        "attempt_id": "attempt-1",
        "recording_profile_id": "fixture-profile-sha256",
        "calibration_id": "fixture-calibration",
        "project_commit": "a" * 40,
        "policy_checkpoint_id": None,
        "episode_index": 0,
        "started": True,
        "cube_instance_id": "color_a_cube_01",
        "cube_color_id": "color_a",
        "target_bin_color_id": "color_a",
        "actual_bin_color_id": "color_a",
        "initial_region": "left",
        "selection_rule": "single_visible_cube",
        "grasp_attempted": True,
        "grasp_succeeded": True,
        "placement_started": True,
        "released_and_stable": True,
        "observed_outcome": "unknown",
        "observer_frame_id": None,
        "observer_agreement": "unknown",
        "human_outcome": "success",
        "human_intervention": False,
        "end_reason": "normal",
    }
    payload.update(overrides)
    return AttemptLabel.model_validate(payload)


def test_evaluation_preserves_failure_abort_unknown_and_preflight_denominators() -> None:
    labels = [
        _label(),
        _label(
            session_id="session-b",
            scene_id="scene-2",
            attempt_id="attempt-2",
            episode_index=1,
            cube_color_id="color_b",
            target_bin_color_id="color_b",
            actual_bin_color_id="color_c",
            human_outcome="failure",
        ),
        _label(
            session_id="session-c",
            scene_id="scene-3",
            attempt_id="attempt-3",
            episode_index=2,
            placement_started=False,
            released_and_stable=False,
            actual_bin_color_id=None,
            human_outcome="abort",
            end_reason="operator_stop",
        ),
        _label(
            session_id="session-d",
            scene_id="scene-4",
            attempt_id="attempt-4",
            episode_index=3,
            grasp_succeeded=False,
            placement_started=False,
            released_and_stable=False,
            actual_bin_color_id=None,
            human_outcome=None,
            observed_outcome="unknown",
            end_reason="visibility_unknown",
        ),
        _label(
            session_id="session-e",
            scene_id="scene-5",
            attempt_id="preflight-1",
            episode_index=None,
            started=False,
            grasp_attempted=False,
            grasp_succeeded=False,
            placement_started=False,
            released_and_stable=False,
            actual_bin_color_id=None,
            human_outcome=None,
            observed_outcome="abort",
            end_reason="preflight_rejected",
        ),
    ]

    summary = summarize_attempts(labels)
    assert summary.attempts_started == 4
    assert summary.preflight_rejected == 1
    assert summary.correct_placements == 1
    assert summary.placements_started == 2
    assert summary.human_outcomes == {"success": 1, "failure": 1, "abort": 1, "unknown": 1}
    assert summary.confusion_matrix["color_b"]["color_c"] == 1


def test_success_label_requires_correct_stable_unassisted_human_verification() -> None:
    with pytest.raises(ValueError, match="human success"):
        _label(human_intervention=True)
    with pytest.raises(ValueError, match="human success"):
        _label(actual_bin_color_id="color_b")
    with pytest.raises(ValueError, match="human success"):
        _label(released_and_stable=False)
    with pytest.raises(ValueError, match="target bin color"):
        _label(target_bin_color_id="color_b", human_outcome="failure")
    with pytest.raises(ValueError):
        _label(episode_index=True)
    with pytest.raises(ValueError, match="optional identity"):
        _label(observer_frame_id=" ")


def test_split_is_session_grouped_and_stats_are_train_only() -> None:
    labels = [
        _label(attempt_id="a0", episode_index=0, session_id="train-session"),
        _label(attempt_id="a1", episode_index=1, session_id="train-session"),
        _label(attempt_id="a2", episode_index=2, session_id="validation-session"),
        _label(attempt_id="a3", episode_index=3, session_id="test-session"),
    ]
    manifest = build_split_manifest(
        labels,
        profile_sha256="abc123",
        validation_sessions={"validation-session"},
        test_sessions={"test-session"},
    )

    assert [item.episode_index for item in manifest.partitions["train"]] == [0, 1]
    assert [item.episode_index for item in manifest.partitions["validation"]] == [2]
    assert [item.episode_index for item in manifest.partitions["test"]] == [3]
    assert manifest.normalization_stats_source.episode_indices == [0, 1]
    validate_split_manifest(manifest)

    leaked = manifest.model_copy(deep=True)
    leaked.normalization_stats_source.episode_indices.append(2)
    with pytest.raises(ValueError, match="training partition only"):
        validate_split_manifest(leaked)

    with pytest.raises(ValueError, match="cannot be empty"):
        build_split_manifest(
            labels[:2],
            profile_sha256="abc123",
            validation_sessions=set(),
            test_sessions=set(),
        )

    with pytest.raises(ValueError, match="duplicate attempt identity"):
        build_split_manifest(
            [labels[0], _label(attempt_id="a0", episode_index=4, session_id="train-session")],
            profile_sha256="abc123",
            validation_sessions=set(),
            test_sessions=set(),
        )


def test_local_summary_is_hashed_atomic_and_contains_no_absolute_path(tmp_path: Path) -> None:
    profile = _configured_profile()
    labels = [_label()]
    path = write_local_summary(tmp_path, profile, labels)

    assert path == local_summary_path(tmp_path, profile.dataset.repo_id or "")
    assert path.is_file()
    assert profile.dataset.repo_id not in path.name
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["dataset_repo_id"] == profile.dataset.repo_id
    assert payload["profile_sha256"] == profile_fingerprint(profile)
    assert payload["evaluation"]["correct_placements"] == 1
    assert str(tmp_path) not in path.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="not capture-ready"):
        write_local_summary(tmp_path, profile.model_copy(update={"stage": "C0"}), labels)


def test_local_labels_reject_wrong_identity_and_duplicate_attempt(tmp_path: Path) -> None:
    profile = _configured_profile()
    label = _label()
    labels_path = append_attempt_label(tmp_path, profile, label)

    assert labels_path == local_labels_path(tmp_path, profile.dataset.repo_id or "")
    assert profile.dataset.repo_id not in labels_path.name
    assert load_attempt_labels(labels_path) == [label]
    with pytest.raises(ValueError, match="duplicate attempt identity"):
        append_attempt_label(tmp_path, profile, label)

    wrong_layout = _label(attempt_id="wrong-layout", episode_index=1, layout_id="other-layout")
    with pytest.raises(ValueError, match="layout_id does not match"):
        append_attempt_label(tmp_path, profile, wrong_layout)

    wrong_instance = _label(
        attempt_id="wrong-instance",
        episode_index=1,
        cube_instance_id="color_b_cube_01",
    )
    with pytest.raises(ValueError, match="cube instance"):
        append_attempt_label(tmp_path, profile, wrong_instance)


def test_formal_split_file_is_hashed_and_contains_all_partitions(tmp_path: Path) -> None:
    profile = _configured_profile()
    labels = [
        _label(attempt_id="train", episode_index=0, session_id="train-session"),
        _label(attempt_id="validation", episode_index=1, session_id="validation-session"),
        _label(attempt_id="test", episode_index=2, session_id="test-session"),
    ]

    split_path = write_local_split_manifest(
        tmp_path,
        profile,
        labels,
        validation_sessions={"validation-session"},
        test_sessions={"test-session"},
    )
    assert split_path == local_split_manifest_path(tmp_path, profile.dataset.repo_id or "")
    assert str(tmp_path) not in split_path.read_text(encoding="utf-8")


def test_pilot_summary_cli_does_not_claim_a_formal_split(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile = _configured_profile()
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    evidence_root = tmp_path / "evidence"
    append_attempt_label(evidence_root, profile, _label())
    monkeypatch.setenv("LELAB_RECORDING_EVIDENCE_ROOT", str(evidence_root))

    assert color_sorting_main(["summarize-labels", str(profile_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["split_file"] is None
    assert local_summary_path(evidence_root, profile.dataset.repo_id or "").is_file()
    assert not local_split_manifest_path(evidence_root, profile.dataset.repo_id or "").exists()


def test_saved_image_cli_uses_the_pure_observer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(_configured_profile().model_dump_json(indent=2), encoding="utf-8")
    image_path = tmp_path / "front.png"
    frame = np.zeros((200, 300, 3), dtype=np.uint8)
    cv2.rectangle(frame, (45, 70), (75, 100), (0, 0, 255), -1)
    assert cv2.imwrite(str(image_path), frame)
    monkeypatch.setattr(cv2, "VideoCapture", lambda *_a, **_k: pytest.fail("camera was opened"))

    assert color_sorting_main(["observe-image", str(profile_path), str(image_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "valid"
    assert output["detections"][0]["color_id"] == "color_a"
