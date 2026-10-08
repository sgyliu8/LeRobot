"""Run from the project root: python -m so101_lab.data_preparation_cli --help."""

from __future__ import annotations

import argparse
import json

from .data_preparation import freeze_split, inspect_dataset, label_episode, preparation_path, read_review


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Review local episodes without changing raw data or starting training")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="read-only technical audit; initialize pending human reviews")
    inspect.add_argument("repo_id")
    inspect.add_argument("--refresh", action="store_true", help="archive old decisions/split and start a new review")
    status = commands.add_parser("status", help="show all human decisions and recording-session identities")
    status.add_argument("repo_id")
    label = commands.add_parser("label", help="record a human decision for a zero-based Dataset episode index")
    label.add_argument("repo_id")
    label.add_argument("--episode", type=int, required=True)
    label.add_argument("--decision", choices=["keep", "exclude"], required=True)
    label.add_argument("--outcome", choices=["success", "failure", "aborted", "unknown"], required=True)
    label.add_argument("--intervention", choices=["yes", "no", "unknown"], required=True)
    label.add_argument("--reason", required=True)
    freeze = commands.add_parser("freeze", help="freeze three disjoint recording-session partitions for local ACT")
    freeze.add_argument("repo_id")
    freeze.add_argument("--validation-session", action="append", required=True)
    freeze.add_argument("--test-session", action="append", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            report = inspect_dataset(args.repo_id, refresh=args.refresh)
            print(json.dumps({key: report[key] for key in (
                "status", "episodes", "frames", "failures", "read_only_manifest_unchanged"
            )}, indent=2, ensure_ascii=False))
            print(f"Local report: {preparation_path(args.repo_id, 'audit.json')}")
            return 0 if report["status"] == "PASS" else 1
        if args.command == "label":
            value = label_episode(
                args.repo_id, args.episode, decision=args.decision, outcome=args.outcome,
                intervention={"yes": True, "no": False, "unknown": None}[args.intervention], reason=args.reason,
            )
        elif args.command == "freeze":
            value = freeze_split(args.repo_id, set(args.validation_session), set(args.test_session))
        else:
            value = read_review(args.repo_id)
        print(value.model_dump_json(indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(f"BLOCKED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
