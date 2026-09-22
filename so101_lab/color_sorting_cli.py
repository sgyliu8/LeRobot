"""Command-line entry points for local color-sorting evidence."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import cv2

from .color_sorting import (
    AttemptLabel,
    append_attempt_label,
    load_attempt_labels,
    load_profile,
    local_labels_path,
    observe_frame,
    profile_fingerprint,
    write_local_split_manifest,
    write_local_summary,
)


def _evidence_root() -> Path:
    configured = os.environ.get("LELAB_RECORDING_EVIDENCE_ROOT")
    root = Path(configured) if configured else Path.cwd() / ".local" / "evidence" / "recordings"
    return root.expanduser().resolve()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate color_sorting_v1 profiles and local evidence")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-profile", help="validate schema and list capture blockers")
    validate.add_argument("profile", type=Path)
    validate.add_argument("--require-ready", action="store_true")

    observe = subparsers.add_parser("observe-image", help="inspect one saved image; never opens a camera")
    observe.add_argument("profile", type=Path)
    observe.add_argument("image", type=Path)
    observe.add_argument("--camera-key", choices=("arm", "table_veiw"), default="table_veiw")
    observe.add_argument("--color-order", choices=("BGR", "RGB"), default="BGR")

    label = subparsers.add_parser("append-label", help="append one validated attempt label locally")
    label.add_argument("profile", type=Path)
    label.add_argument("label", type=Path, help="one JSON object matching the attempt-label contract")

    subparsers.add_parser(
        "summarize-labels",
        help="write a local result summary without claiming a formal train/validation/test split",
    ).add_argument("profile", type=Path)

    audit = subparsers.add_parser("audit-labels", help="write a local summary and frozen session split")
    audit.add_argument("profile", type=Path)
    audit.add_argument("--validation-session", action="append", default=[])
    audit.add_argument("--test-session", action="append", default=[])

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    profile = load_profile(args.profile)
    root = _evidence_root()

    if args.command == "validate-profile":
        issues = profile.capture_readiness_issues()
        print(json.dumps({
            "task_id": profile.task_id,
            "stage": profile.stage,
            "profile_sha256": profile_fingerprint(profile),
            "capture_ready": not issues,
            "issues": issues,
        }, indent=2))
        return 2 if args.require_ready and issues else 0

    if args.command == "observe-image":
        frame = cv2.imread(str(args.image), cv2.IMREAD_COLOR)
        if frame is None:
            raise SystemExit(f"could not decode image: {args.image}")
        if args.color_order == "RGB":
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        now = time.time()
        observed = observe_frame(
            frame,
            profile,
            camera_key=args.camera_key,
            frame_id=args.image.name,
            captured_at_s=now,
            now_s=now,
            color_order=args.color_order,
        )
        print(observed.model_dump_json(indent=2))
        return 0 if observed.status == "valid" else 3

    if not profile.dataset.repo_id:
        raise SystemExit("dataset.repo_id must be frozen for label operations")

    if args.command == "append-label":
        raw = json.loads(args.label.read_text(encoding="utf-8"))
        label = AttemptLabel.model_validate(raw)
        path = append_attempt_label(root, profile, label)
        print(json.dumps({"saved": True, "label_count": len(load_attempt_labels(path))}))
        return 0

    labels_path = local_labels_path(root, profile.dataset.repo_id)
    if not labels_path.is_file():
        raise SystemExit("no local attempt labels exist for this dataset")
    labels = load_attempt_labels(labels_path)
    if args.command == "summarize-labels":
        summary_path = write_local_summary(root, profile, labels)
        print(json.dumps({
            "dataset_repo_id": profile.dataset.repo_id,
            "label_count": len(labels),
            "summary_file": summary_path.name,
            "split_file": None,
        }, indent=2))
        return 0

    split_path = write_local_split_manifest(
        root,
        profile,
        labels,
        validation_sessions=set(args.validation_session),
        test_sessions=set(args.test_session),
    )
    summary_path = write_local_summary(root, profile, labels)
    print(json.dumps({
        "dataset_repo_id": profile.dataset.repo_id,
        "label_count": len(labels),
        "summary_file": summary_path.name,
        "split_file": split_path.name,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
