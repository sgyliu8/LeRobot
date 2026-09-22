"""Local-first contracts for the ``color_sorting_v1`` task.

The observer in this module consumes an already-owned image array.  It never
constructs a camera, controls a robot, or promotes a visual heuristic to a task
success label.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Annotated, Literal

import cv2
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CameraKey = Literal["arm", "table_veiw"]
ColorOrder = Literal["BGR", "RGB"]
HumanOutcome = Literal["success", "failure", "abort", "unknown"]
Stage = Literal["C0", "C1", "C2", "C3", "C4"]
PositiveStrictInt = Annotated[int, Field(strict=True, gt=0)]
NonNegativeStrictInt = Annotated[int, Field(strict=True, ge=0)]
StrictIntValue = Annotated[int, Field(strict=True)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HSVRange(StrictModel):
    lower: tuple[StrictIntValue, StrictIntValue, StrictIntValue]
    upper: tuple[StrictIntValue, StrictIntValue, StrictIntValue]

    @model_validator(mode="after")
    def validate_bounds(self) -> "HSVRange":
        limits = (179, 255, 255)
        for name, value in (("lower", self.lower), ("upper", self.upper)):
            if any(channel < 0 or channel > limit for channel, limit in zip(value, limits, strict=True)):
                raise ValueError(f"{name} is outside OpenCV HSV bounds")
        if any(low > high for low, high in zip(self.lower, self.upper, strict=True)):
            raise ValueError("HSV wrap-around must be represented by two ranges")
        return self


class ColorSpec(StrictModel):
    id: str
    display_name: str | None = None
    hsv_ranges: list[HSVRange] = Field(default_factory=list)
    instance_ids: list[str] = Field(default_factory=list)


class BinSpec(StrictModel):
    color_id: str
    opening_size_mm: tuple[float, float, float] | None = None
    same_color_interior: Literal[True] = True

    @model_validator(mode="after")
    def validate_size(self) -> "BinSpec":
        if self.opening_size_mm is not None and any(
            not math.isfinite(value) or value <= 0 for value in self.opening_size_mm
        ):
            raise ValueError("bin opening dimensions must be finite and positive")
        return self


class EntitySpec(StrictModel):
    cube_size_mm: tuple[float, float, float] | None = None
    colors: list[ColorSpec]
    bins: list[BinSpec]

    @model_validator(mode="after")
    def validate_entities(self) -> "EntitySpec":
        if self.cube_size_mm is not None and any(
            not math.isfinite(value) or value <= 0 for value in self.cube_size_mm
        ):
            raise ValueError("cube dimensions must be finite and positive")
        color_ids = [color.id for color in self.colors]
        if len(color_ids) != 3 or len(set(color_ids)) != 3:
            raise ValueError("color_sorting_v1 requires exactly three unique colors")
        if {item.color_id for item in self.bins} != set(color_ids) or len(self.bins) != 3:
            raise ValueError("bins must map one-to-one to the three colors")
        instance_ids = [item for color in self.colors for item in color.instance_ids]
        if len(instance_ids) != len(set(instance_ids)):
            raise ValueError("cube instance IDs must be unique")
        return self


class NormalizedROI(StrictModel):
    x: float = Field(ge=0.0, lt=1.0, allow_inf_nan=False)
    y: float = Field(ge=0.0, lt=1.0, allow_inf_nan=False)
    width: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)
    height: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_extent(self) -> "NormalizedROI":
        if self.x + self.width > 1.0 or self.y + self.height > 1.0:
            raise ValueError("ROI extends beyond the normalized image")
        return self


class BinRegion(StrictModel):
    color_id: str
    interior_roi: NormalizedROI | None = None
    rim_roi: NormalizedROI | None = None


class SceneSpec(StrictModel):
    layout_id: str | None = None
    observer_camera_key: Literal["table_veiw"] = "table_veiw"
    source_roi: NormalizedROI | None = None
    bin_regions: list[BinRegion]
    gripper_exclusion_rois: list[NormalizedROI] = Field(default_factory=list)
    max_objects: PositiveStrictInt = 1
    selection_rule: Literal["single_visible_cube", "leftmost_front_cube"] = "single_visible_cube"
    frame_max_age_s: float = Field(default=0.5, gt=0.0, allow_inf_nan=False)
    min_component_area_fraction: float = Field(default=0.002, gt=0.0, lt=1.0, allow_inf_nan=False)
    max_component_area_fraction: float = Field(default=0.08, gt=0.0, lt=1.0, allow_inf_nan=False)


class DatasetSpec(StrictModel):
    repo_id: str | None = None
    single_task: Literal["Sort the visible cube into the bin with the same color."] = (
        "Sort the visible cube into the bin with the same color."
    )
    fps: PositiveStrictInt = 15
    camera_aliases: dict[CameraKey, str]
    hue_augmentation: Literal[False] = False
    grayscale_augmentation: Literal[False] = False
    color_changing_augmentation: Literal[False] = False

    @model_validator(mode="after")
    def validate_cameras(self) -> "DatasetSpec":
        expected = {"arm": "wrist", "table_veiw": "front"}
        if self.camera_aliases != expected:
            raise ValueError(f"camera aliases must remain {expected}")
        if self.repo_id is not None and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*", self.repo_id
        ):
            raise ValueError("dataset.repo_id must be the exact '<namespace>/<name>' identity")
        return self


class PolicySpec(StrictModel):
    type: Literal["act"] = "act"
    chunk_size: PositiveStrictInt = 32
    n_action_steps: PositiveStrictInt = 8
    conditioning: Literal["rgb_and_robot_state"] = "rgb_and_robot_state"
    task_text_consumed: Literal[False] = False
    checkpoint_id: str | None = None

    @model_validator(mode="after")
    def validate_execution_prefix(self) -> "PolicySpec":
        if self.n_action_steps > self.chunk_size:
            raise ValueError("ACT n_action_steps cannot exceed chunk_size")
        return self


class ColorSortingProfile(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    task_id: Literal["color_sorting_v1"] = "color_sorting_v1"
    stage: Stage = "C0"
    dataset: DatasetSpec
    entities: EntitySpec
    scene: SceneSpec
    policy: PolicySpec = Field(default_factory=PolicySpec)
    recording_profile_id: str | None = None
    calibration_id: str | None = None
    project_commit: str | None = None

    @model_validator(mode="after")
    def validate_relations(self) -> "ColorSortingProfile":
        identity_values = {
            "scene.layout_id": self.scene.layout_id,
            "recording_profile_id": self.recording_profile_id,
            "calibration_id": self.calibration_id,
            "policy.checkpoint_id": self.policy.checkpoint_id,
        }
        for name, value in identity_values.items():
            if value is not None and (not value.strip() or value != value.strip()):
                raise ValueError(f"{name} must be non-empty and trimmed when set")
        for color in self.entities.colors:
            texts = [color.id, *color.instance_ids]
            if color.display_name is not None:
                texts.append(color.display_name)
            if any(not value.strip() or value != value.strip() for value in texts):
                raise ValueError("color and instance identities must be non-empty and trimmed")
        color_ids = {color.id for color in self.entities.colors}
        display_names = [color.display_name.casefold() for color in self.entities.colors if color.display_name]
        if len(display_names) != len(set(display_names)):
            raise ValueError("configured color display names must be unique")
        region_ids = [region.color_id for region in self.scene.bin_regions]
        if len(region_ids) != 3 or set(region_ids) != color_ids:
            raise ValueError("bin regions must map one-to-one to configured colors")
        if self.scene.max_component_area_fraction <= self.scene.min_component_area_fraction:
            raise ValueError("maximum component area must exceed minimum component area")
        configured_ranges = [
            (color.id, hsv_range)
            for color in self.entities.colors
            for hsv_range in color.hsv_ranges
        ]
        for index, (left_id, left) in enumerate(configured_ranges):
            for right_id, right in configured_ranges[index + 1 :]:
                if left_id == right_id:
                    continue
                overlaps = all(
                    left.lower[channel] <= right.upper[channel]
                    and right.lower[channel] <= left.upper[channel]
                    for channel in range(3)
                )
                if overlaps:
                    raise ValueError(f"HSV ranges overlap for {left_id} and {right_id}")
        for region in self.scene.bin_regions:
            if region.interior_roi is not None and region.rim_roi is not None:
                interior, rim = region.interior_roi, region.rim_roi
                if not (
                    rim.x <= interior.x
                    and rim.y <= interior.y
                    and rim.x + rim.width >= interior.x + interior.width
                    and rim.y + rim.height >= interior.y + interior.height
                ):
                    raise ValueError(f"bin rim ROI must contain its interior for {region.color_id}")
        task_regions = [
            ("source", self.scene.source_roi),
            *[(f"bin:{item.color_id}", item.interior_roi) for item in self.scene.bin_regions],
        ]
        configured_regions = [(name, roi) for name, roi in task_regions if roi is not None]
        for index, (left_name, left) in enumerate(configured_regions):
            for right_name, right in configured_regions[index + 1 :]:
                if (
                    left.x < right.x + right.width
                    and right.x < left.x + left.width
                    and left.y < right.y + right.height
                    and right.y < left.y + left.height
                ):
                    raise ValueError(f"task ROIs overlap: {left_name} and {right_name}")
        if self.stage == "C1" and (
            self.scene.max_objects != 1 or self.scene.selection_rule != "single_visible_cube"
        ):
            raise ValueError("C1 requires one visible cube and the single_visible_cube rule")
        if self.project_commit is not None and not re.fullmatch(r"[0-9a-f]{40}", self.project_commit):
            raise ValueError("project_commit must be a full lowercase Git commit")
        return self

    def capture_readiness_issues(self, *, new_dataset: bool = False) -> list[str]:
        issues: list[str] = []
        if self.stage == "C0":
            issues.append("task stage is C0; select an attended capture stage")
        if not self.dataset.repo_id and not new_dataset:
            issues.append("dataset.repo_id is not frozen")
        if self.entities.cube_size_mm is None:
            issues.append("actual cube dimensions are not frozen")
        for color in self.entities.colors:
            if not color.display_name or not color.hsv_ranges or not color.instance_ids:
                issues.append(f"actual color definition is not frozen for {color.id}")
        for item in self.entities.bins:
            if item.opening_size_mm is None:
                issues.append(f"actual bin dimensions are not frozen for {item.color_id}")
        if self.scene.source_roi is None:
            issues.append("source ROI is not frozen")
        if not self.scene.layout_id:
            issues.append("scene layout identity is not frozen")
        if not self.scene.gripper_exclusion_rois:
            issues.append("gripper exclusion ROI/strategy is not frozen")
        for region in self.scene.bin_regions:
            if region.interior_roi is None or region.rim_roi is None:
                issues.append(f"bin interior/rim ROIs are not frozen for {region.color_id}")
        if not self.recording_profile_id:
            issues.append("recording profile identity is not frozen")
        if not self.calibration_id:
            issues.append("calibration identity is not frozen")
        if not self.project_commit:
            issues.append("project commit is not frozen")
        return issues


class Detection(StrictModel):
    color_id: str
    region: str
    bbox_xywh: tuple[int, int, int, int]
    center_xy: tuple[float, float]
    area_px: float
    validity: Literal["valid", "unknown"]


class Observation(StrictModel):
    camera_key: CameraKey
    frame_id: str
    captured_at_s: float
    status: Literal["valid", "unknown"]
    issues: list[str]
    detections: list[Detection]


def load_profile(path: Path | str) -> ColorSortingProfile:
    return ColorSortingProfile.model_validate_json(Path(path).read_text(encoding="utf-8"))


def profile_fingerprint(profile: ColorSortingProfile) -> str:
    canonical = json.dumps(profile.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _pixel_roi(roi: NormalizedROI, width: int, height: int) -> tuple[int, int, int, int]:
    x0 = max(0, min(width - 1, round(roi.x * width)))
    y0 = max(0, min(height - 1, round(roi.y * height)))
    x1 = max(x0 + 1, min(width, round((roi.x + roi.width) * width)))
    y1 = max(y0 + 1, min(height, round((roi.y + roi.height) * height)))
    return x0, y0, x1, y1


def _append_issue(issues: list[str], issue: str) -> None:
    if issue not in issues:
        issues.append(issue)


def observe_frame(
    frame: np.ndarray,
    profile: ColorSortingProfile,
    *,
    camera_key: CameraKey,
    frame_id: str,
    captured_at_s: float,
    now_s: float,
    color_order: ColorOrder = "BGR",
) -> Observation:
    """Inspect a caller-owned frame without acquiring or repairing any source."""

    base = {
        "camera_key": camera_key,
        "frame_id": frame_id,
        "captured_at_s": captured_at_s,
    }
    if (
        not math.isfinite(captured_at_s)
        or not math.isfinite(now_s)
        or now_s < captured_at_s
    ):
        return Observation(**base, status="unknown", issues=["invalid_frame_timestamp"], detections=[])
    if now_s - captured_at_s > profile.scene.frame_max_age_s:
        return Observation(**base, status="unknown", issues=["stale_frame"], detections=[])
    if (
        not isinstance(frame, np.ndarray)
        or frame.ndim != 3
        or frame.shape[2] != 3
        or frame.size == 0
        or frame.dtype != np.uint8
    ):
        return Observation(**base, status="unknown", issues=["invalid_frame"], detections=[])
    if camera_key != profile.scene.observer_camera_key:
        return Observation(
            **base,
            status="unknown",
            issues=["camera_role_not_configured"],
            detections=[],
        )

    bgr = frame if color_order == "BGR" else cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    height, width = frame.shape[:2]
    excluded = np.zeros((height, width), dtype=np.uint8)
    for exclusion_roi in profile.scene.gripper_exclusion_rois:
        x0, y0, x1, y1 = _pixel_roi(exclusion_roi, width, height)
        excluded[y0:y1, x0:x1] = 255
    frame_area = float(height * width)
    min_area = profile.scene.min_component_area_fraction * frame_area
    max_area = profile.scene.max_component_area_fraction * frame_area
    color_specs = {item.id: item for item in profile.entities.colors}
    bin_specs = {item.color_id: item for item in profile.entities.bins}
    regions: list[tuple[str, NormalizedROI, str | None]] = []
    if profile.scene.source_roi is not None:
        regions.append(("source", profile.scene.source_roi, None))
    for region in profile.scene.bin_regions:
        if region.interior_roi is not None:
            regions.append((f"bin:{region.color_id}", region.interior_roi, region.color_id))

    detections: list[Detection] = []
    issues: list[str] = []
    for region_name, roi, bin_color_id in regions:
        x0, y0, x1, y1 = _pixel_roi(roi, width, height)
        crop = hsv[y0:y1, x0:x1]
        excluded_crop = excluded[y0:y1, x0:x1]
        allowed = cv2.bitwise_not(excluded_crop)
        known_union = np.zeros(crop.shape[:2], dtype=np.uint8)
        for color_id, spec in color_specs.items():
            mask = np.zeros(crop.shape[:2], dtype=np.uint8)
            for hsv_range in spec.hsv_ranges:
                mask = cv2.bitwise_or(
                    mask,
                    cv2.inRange(
                        crop,
                        np.asarray(hsv_range.lower, dtype=np.uint8),
                        np.asarray(hsv_range.upper, dtype=np.uint8),
                    ),
                )
            mask = cv2.bitwise_and(mask, allowed)
            known_union = cv2.bitwise_or(known_union, mask)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                area = float(cv2.contourArea(contour))
                if area < min_area:
                    continue
                local_x, local_y, box_w, box_h = cv2.boundingRect(contour)
                touches_boundary = (
                    local_x <= 0
                    or local_y <= 0
                    or local_x + box_w >= crop.shape[1]
                    or local_y + box_h >= crop.shape[0]
                )
                contour_mask = np.zeros(crop.shape[:2], dtype=np.uint8)
                cv2.drawContours(contour_mask, [contour], -1, 255, thickness=-1)
                touches_exclusion = bool(
                    np.any(
                        cv2.bitwise_and(
                            cv2.dilate(contour_mask, np.ones((3, 3), dtype=np.uint8)),
                            excluded_crop,
                        )
                    )
                )
                validity: Literal["valid", "unknown"] = "valid"
                if touches_boundary or touches_exclusion:
                    validity = "unknown"
                    _append_issue(issues, "occluded_or_outside_roi")
                if area > max_area:
                    validity = "unknown"
                    _append_issue(issues, "merged_or_background_component")
                if (
                    bin_color_id == color_id
                    and bin_specs[bin_color_id].same_color_interior
                ):
                    validity = "unknown"
                    _append_issue(issues, "manual_verification_required")
                moments = cv2.moments(contour)
                if moments["m00"]:
                    center_x = x0 + moments["m10"] / moments["m00"]
                    center_y = y0 + moments["m01"] / moments["m00"]
                else:
                    center_x = x0 + local_x + box_w / 2
                    center_y = y0 + local_y + box_h / 2
                detections.append(
                    Detection(
                        color_id=color_id,
                        region=region_name,
                        bbox_xywh=(x0 + local_x, y0 + local_y, box_w, box_h),
                        center_xy=(center_x, center_y),
                        area_px=area,
                        validity=validity,
                    )
                )

        saturated = cv2.inRange(crop, np.asarray((0, 100, 60), np.uint8), np.asarray((179, 255, 255), np.uint8))
        saturated = cv2.bitwise_and(saturated, allowed)
        unmatched = cv2.bitwise_and(saturated, cv2.bitwise_not(known_union))
        contours, _ = cv2.findContours(unmatched, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if any(float(cv2.contourArea(contour)) >= min_area for contour in contours):
            _append_issue(issues, "unknown_color")

    if (
        profile.stage == "C1" and len(detections) != 1
    ) or len(detections) > profile.scene.max_objects:
        _append_issue(issues, "unexpected_object_count")
    detections.sort(key=lambda item: (item.region, item.color_id, item.bbox_xywh))
    return Observation(
        **base,
        status="unknown" if issues else "valid",
        issues=issues,
        detections=detections,
    )


class AttemptLabel(StrictModel):
    dataset_repo_id: str
    session_id: str
    scene_id: str
    layout_id: str
    attempt_id: str
    recording_profile_id: str
    calibration_id: str
    project_commit: str
    policy_checkpoint_id: str | None = None
    episode_index: NonNegativeStrictInt | None = None
    started: bool
    cube_instance_id: str
    cube_color_id: str
    target_bin_color_id: str
    actual_bin_color_id: str | None = None
    initial_region: str
    selection_rule: str
    grasp_attempted: bool
    grasp_succeeded: bool
    placement_started: bool
    released_and_stable: bool
    observed_outcome: HumanOutcome
    observer_frame_id: str | None = None
    observer_agreement: Literal["agree", "disagree", "unknown"] = "unknown"
    human_outcome: HumanOutcome | None = None
    human_intervention: bool
    end_reason: str

    @field_validator(
        "dataset_repo_id",
        "session_id",
        "scene_id",
        "layout_id",
        "attempt_id",
        "recording_profile_id",
        "calibration_id",
        "cube_instance_id",
        "cube_color_id",
        "target_bin_color_id",
        "initial_region",
        "selection_rule",
        "end_reason",
    )
    @classmethod
    def validate_identity_text(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("identity fields must be non-empty and trimmed")
        return value

    @field_validator("policy_checkpoint_id", "observer_frame_id")
    @classmethod
    def validate_optional_identity_text(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or value != value.strip()):
            raise ValueError("optional identity fields must be non-empty and trimmed when set")
        return value

    @field_validator("project_commit")
    @classmethod
    def validate_project_commit(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{40}", value):
            raise ValueError("project_commit must be a full lowercase Git commit")
        return value

    @model_validator(mode="after")
    def validate_attempt(self) -> "AttemptLabel":
        if self.target_bin_color_id != self.cube_color_id:
            raise ValueError("target bin color must match the demonstrated cube color")
        if not self.started and self.episode_index is not None:
            raise ValueError("a preflight-rejected attempt cannot identify a saved episode")
        if self.grasp_succeeded and not self.grasp_attempted:
            raise ValueError("grasp_succeeded requires grasp_attempted")
        if self.placement_started and not self.grasp_succeeded:
            raise ValueError("placement_started requires grasp_succeeded")
        if self.released_and_stable and not self.placement_started:
            raise ValueError("released_and_stable requires placement_started")
        if self.human_outcome == "success" and not (
            self.started
            and self.actual_bin_color_id == self.target_bin_color_id
            and self.released_and_stable
            and not self.human_intervention
        ):
            raise ValueError("human success requires a correct, stable, unassisted placement")
        return self


class EvaluationSummary(StrictModel):
    attempts_total: int
    attempts_started: int
    preflight_rejected: int
    started_without_media: int
    grasp_attempts: int
    grasp_successes: int
    interventions: int
    placements_started: int
    correct_placements: int
    human_outcomes: dict[str, int]
    observed_outcomes: dict[str, int]
    confusion_matrix: dict[str, dict[str, int]]


def summarize_attempts(labels: list[AttemptLabel]) -> EvaluationSummary:
    seen: set[tuple[str, str, str]] = set()
    episodes: set[tuple[str, int]] = set()
    for item in labels:
        attempt_key = (item.dataset_repo_id, item.session_id, item.attempt_id)
        if attempt_key in seen:
            raise ValueError(f"duplicate attempt identity: {attempt_key}")
        seen.add(attempt_key)
        if item.episode_index is not None:
            episode_key = (item.dataset_repo_id, item.episode_index)
            if episode_key in episodes:
                raise ValueError(f"duplicate episode identity: {episode_key}")
            episodes.add(episode_key)

    started = [item for item in labels if item.started]
    human_counts = Counter((item.human_outcome or "unknown") for item in started)
    observed_counts = Counter(item.observed_outcome for item in started)
    confusion: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for item in started:
        if item.actual_bin_color_id is not None:
            confusion[item.cube_color_id][item.actual_bin_color_id] += 1
    outcomes = ("success", "failure", "abort", "unknown")
    return EvaluationSummary(
        attempts_total=len(labels),
        attempts_started=len(started),
        preflight_rejected=sum(not item.started for item in labels),
        started_without_media=sum(item.episode_index is None for item in started),
        grasp_attempts=sum(item.grasp_attempted for item in started),
        grasp_successes=sum(item.grasp_succeeded for item in started),
        interventions=sum(item.human_intervention for item in started),
        placements_started=sum(item.placement_started for item in started),
        correct_placements=sum(item.human_outcome == "success" for item in started),
        human_outcomes={outcome: human_counts[outcome] for outcome in outcomes},
        observed_outcomes={outcome: observed_counts[outcome] for outcome in outcomes},
        confusion_matrix={source: dict(targets) for source, targets in sorted(confusion.items())},
    )


class EpisodeIdentity(StrictModel):
    dataset_repo_id: str
    session_id: str
    episode_index: NonNegativeStrictInt


class NormalizationStatsSource(StrictModel):
    partition: Literal["train"] = "train"
    episode_indices: list[int]


class SplitManifest(StrictModel):
    schema_version: Literal["1.1"] = "1.1"
    profile_sha256: str
    partitions: dict[Literal["train", "validation", "test"], list[EpisodeIdentity]]
    normalization_stats_source: NormalizationStatsSource
    training_inclusion: Literal["human_success_unassisted"] = "human_success_unassisted"
    excluded_training_episodes: list[int] = Field(default_factory=list)


def build_split_manifest(
    labels: list[AttemptLabel],
    *,
    profile_sha256: str,
    validation_sessions: set[str],
    test_sessions: set[str],
) -> SplitManifest:
    summarize_attempts(labels)
    if validation_sessions & test_sessions:
        raise ValueError("a session cannot be both validation and test")
    partitions: dict[str, list[EpisodeIdentity]] = {"train": [], "validation": [], "test": []}
    seen_episodes: set[tuple[str, int]] = set()
    excluded: list[int] = []
    for item in labels:
        if not item.started or item.episode_index is None:
            continue
        key = (item.dataset_repo_id, item.episode_index)
        if key in seen_episodes:
            raise ValueError(f"duplicate episode identity: {key}")
        seen_episodes.add(key)
        partition = (
            "test"
            if item.session_id in test_sessions
            else "validation"
            if item.session_id in validation_sessions
            else "train"
        )
        # Preserve every attempt in evaluation; initial behavior cloning learns
        # only reviewed, unassisted successful demonstrations.
        if partition == "train" and (item.human_outcome != "success" or item.human_intervention):
            excluded.append(item.episode_index)
            continue
        partitions[partition].append(
            EpisodeIdentity(
                dataset_repo_id=item.dataset_repo_id,
                session_id=item.session_id,
                episode_index=item.episode_index,
            )
        )
    for items in partitions.values():
        items.sort(key=lambda item: (item.dataset_repo_id, item.episode_index))
    manifest = SplitManifest(
        profile_sha256=profile_sha256,
        partitions=partitions,
        normalization_stats_source=NormalizationStatsSource(
            episode_indices=[item.episode_index for item in partitions["train"]]
        ),
        excluded_training_episodes=sorted(excluded),
    )
    validate_split_manifest(manifest)
    return manifest


def validate_split_manifest(manifest: SplitManifest) -> None:
    expected = {"train", "validation", "test"}
    if set(manifest.partitions) != expected:
        raise ValueError(f"split partitions must be exactly {sorted(expected)}")
    empty_partitions = sorted(name for name, items in manifest.partitions.items() if not items)
    if empty_partitions:
        raise ValueError(f"formal split partitions cannot be empty: {empty_partitions}")
    seen_episodes: set[tuple[str, int]] = set()
    session_partition: dict[tuple[str, str], str] = {}
    dataset_ids: set[str] = set()
    for partition, items in manifest.partitions.items():
        for item in items:
            dataset_ids.add(item.dataset_repo_id)
            episode_key = (item.dataset_repo_id, item.episode_index)
            if episode_key in seen_episodes:
                raise ValueError("an episode appears in more than one partition")
            seen_episodes.add(episode_key)
            session_key = (item.dataset_repo_id, item.session_id)
            previous = session_partition.setdefault(session_key, partition)
            if previous != partition:
                raise ValueError("a session appears in more than one partition")
    if len(dataset_ids) != 1:
        raise ValueError("a formal split must contain exactly one dataset identity")
    excluded = manifest.excluded_training_episodes
    if len(excluded) != len(set(excluded)) or any(type(i) is not int or i < 0 for i in excluded):
        raise ValueError("excluded episodes must be unique nonnegative integers")
    if set(excluded) & {item.episode_index for items in manifest.partitions.values() for item in items}:
        raise ValueError("excluded training episodes cannot enter any partition")
    train_indices = [item.episode_index for item in manifest.partitions["train"]]
    if manifest.normalization_stats_source.episode_indices != train_indices:
        raise ValueError("normalization statistics must use the training partition only")


def local_summary_path(root: Path | str, dataset_repo_id: str) -> Path:
    digest = hashlib.sha256(dataset_repo_id.encode("utf-8")).hexdigest()
    return Path(root) / "color_sorting" / f"{digest}.json"


def local_labels_path(root: Path | str, dataset_repo_id: str) -> Path:
    digest = hashlib.sha256(dataset_repo_id.encode("utf-8")).hexdigest()
    return Path(root) / "color_sorting" / f"{digest}.labels.jsonl"


def local_split_manifest_path(root: Path | str, dataset_repo_id: str) -> Path:
    digest = hashlib.sha256(dataset_repo_id.encode("utf-8")).hexdigest()
    return Path(root) / "color_sorting" / f"{digest}.splits.json"


def load_attempt_labels(path: Path | str) -> list[AttemptLabel]:
    labels: list[AttemptLabel] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            labels.append(AttemptLabel.model_validate_json(line))
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid attempt label on line {line_number}: {exc}") from exc
    summarize_attempts(labels)
    return labels


def _validate_labels_against_profile(
    profile: ColorSortingProfile,
    labels: list[AttemptLabel],
) -> None:
    readiness_issues = profile.capture_readiness_issues()
    if readiness_issues:
        raise ValueError(f"profile is not capture-ready: {readiness_issues}")
    if not profile.dataset.repo_id:
        raise ValueError("dataset.repo_id must be frozen before validating labels")
    required_profile_identities = {
        "layout_id": profile.scene.layout_id,
        "recording_profile_id": profile.recording_profile_id,
        "calibration_id": profile.calibration_id,
        "project_commit": profile.project_commit,
    }
    missing = [name for name, value in required_profile_identities.items() if not value]
    if missing:
        raise ValueError(f"profile identities must be frozen before writing evidence: {missing}")
    colors = {item.id: set(item.instance_ids) for item in profile.entities.colors}
    for item in labels:
        if item.dataset_repo_id != profile.dataset.repo_id:
            raise ValueError("attempt label dataset identity does not match the profile")
        if item.cube_color_id not in colors:
            raise ValueError("attempt label cube color is not configured by the profile")
        if item.cube_instance_id not in colors[item.cube_color_id]:
            raise ValueError("attempt label cube instance does not match its configured color")
        if item.target_bin_color_id not in colors or (
            item.actual_bin_color_id is not None and item.actual_bin_color_id not in colors
        ):
            raise ValueError("attempt label bin color is not configured by the profile")
        if item.selection_rule != profile.scene.selection_rule:
            raise ValueError("attempt label selection rule does not match the profile")
        for name, expected in required_profile_identities.items():
            if getattr(item, name) != expected:
                raise ValueError(f"attempt label {name} does not match the profile")
        if item.policy_checkpoint_id != profile.policy.checkpoint_id:
            raise ValueError("attempt label policy checkpoint does not match the profile")


def append_attempt_label(
    root: Path | str,
    profile: ColorSortingProfile,
    label: AttemptLabel,
) -> Path:
    if not profile.dataset.repo_id:
        raise ValueError("dataset.repo_id must be frozen before writing labels")
    path = local_labels_path(root, profile.dataset.repo_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_attempt_labels(path) if path.is_file() else []
    combined = [*existing, label]
    _validate_labels_against_profile(profile, combined)
    summarize_attempts(combined)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        "".join(item.model_dump_json() + "\n" for item in combined),
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def write_local_split_manifest(
    root: Path | str,
    profile: ColorSortingProfile,
    labels: list[AttemptLabel],
    *,
    validation_sessions: set[str],
    test_sessions: set[str],
) -> Path:
    if not profile.dataset.repo_id:
        raise ValueError("dataset.repo_id must be frozen before writing a split manifest")
    _validate_labels_against_profile(profile, labels)
    manifest = build_split_manifest(
        labels,
        profile_sha256=profile_fingerprint(profile),
        validation_sessions=validation_sessions,
        test_sessions=test_sessions,
    )
    path = local_split_manifest_path(root, profile.dataset.repo_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest.model_dump_json(indent=2) + "\n"
    if path.exists():
        previous = SplitManifest.model_validate_json(path.read_text(encoding="utf-8"))
        if previous != manifest:
            raise ValueError("split is frozen; use a new evidence namespace for a revised experiment")
        return path
    # Exclusive creation prevents two different freezes from replacing each other.
    with path.open("x", encoding="utf-8") as stream:
        stream.write(payload)
    return path


def write_local_summary(
    root: Path | str,
    profile: ColorSortingProfile,
    labels: list[AttemptLabel],
) -> Path:
    if not profile.dataset.repo_id:
        raise ValueError("dataset.repo_id must be frozen before writing a summary")
    _validate_labels_against_profile(profile, labels)
    path = local_summary_path(root, profile.dataset.repo_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "task_id": profile.task_id,
        "stage": profile.stage,
        "dataset_repo_id": profile.dataset.repo_id,
        "profile_sha256": profile_fingerprint(profile),
        "policy": profile.policy.model_dump(mode="json"),
        "evaluation": summarize_attempts(labels).model_dump(mode="json"),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path
