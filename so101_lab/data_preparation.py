"""Local, non-destructive episode review before behavior-cloning training.

Raw Dataset v3 files are never edited. Human decisions and session splits live
in the recording evidence directory; the official loader remains the reader.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from .color_sorting import EpisodeIdentity, SplitManifest, validate_split_manifest

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
EpisodeIndex = Annotated[int, Field(strict=True, ge=0)]


class EpisodeReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_index: EpisodeIndex
    session_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$")]
    decision: Literal["pending", "keep", "exclude"] = "pending"
    outcome: Literal["unknown", "success", "failure", "aborted"] = "unknown"
    intervention: StrictBool | None = None
    reason: Annotated[str, Field(max_length=500)] = ""

    @model_validator(mode="after")
    def decision_evidence(self):
        if self.decision != "pending" and not self.reason.strip():
            raise ValueError("a human review decision requires a reason")
        if self.decision == "keep" and (self.outcome == "unknown" or self.intervention is None):
            raise ValueError("keep requires a known outcome and intervention status")
        return self


class DatasetReview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    dataset_repo_id: str
    source_sha256: Digest
    profile_sha256: Digest
    audit_status: Literal["PASS", "FAIL"]
    episodes: list[EpisodeReview]

    @model_validator(mode="after")
    def unique_episodes(self):
        indices = [item.episode_index for item in self.episodes]
        if not indices or indices != list(range(len(indices))):
            raise ValueError("review must cover every saved episode in canonical index order")
        return self


class PreparedSplit(SplitManifest):
    # Separate schema preserves existing color-task manifests and job digests.
    schema_version: Literal["2.0"] = "2.0"
    task: Literal["data_review_v1"] = "data_review_v1"
    source_sha256: Digest
    review: DatasetReview


def evidence_root() -> Path:
    return Path(os.environ.get("LELAB_RECORDING_EVIDENCE_ROOT", ".local/evidence/recordings"))


def preparation_path(repo_id: str, name: str = "review.json") -> Path:
    from lelab.episode_media import repo_id_parts, ensure_safe_dataset_path, resolve_dataset_candidate, is_link_or_reparse

    repo_id_parts(repo_id)
    if name not in {"review.json", "audit.json", "split.json"}:
        raise ValueError("unsupported preparation artifact")
    root = evidence_root().absolute()
    if any(is_link_or_reparse(path) for path in [root, *root.parents]):
        raise ValueError("recording evidence root cannot traverse a linked directory")
    raw = resolve_dataset_candidate(repo_id)
    if root.resolve().is_relative_to(raw.resolve()):
        raise ValueError("preparation outputs must be outside the raw Dataset")
    path = root / "preparation" / hashlib.sha256(repo_id.encode()).hexdigest() / name
    return ensure_safe_dataset_path(root, path)


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def source_identity(repo_id: str, sessions: set[str]) -> tuple[str, str]:
    """Portable identity: raw bytes + recording profile + attributed timing traces."""
    from lelab.episode_media import ensure_safe_dataset_path, resolve_dataset_dir
    from tools.audit_dataset import _manifest, _profile_path

    raw = _manifest(resolve_dataset_dir(repo_id))
    files = [[key, value[0], value[2]] for key, value in sorted(raw.items())]
    root = evidence_root().absolute()
    paths = [_profile_path(repo_id).absolute()]
    paths.extend(root / "sidecars" / session / "frames.jsonl" for session in sorted(sessions))
    provenance = []
    for path in paths:
        path = ensure_safe_dataset_path(root, path, require_file=True)
        before = path.stat()
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("recording provenance changed during inspection")
        provenance.append([path.relative_to(root).as_posix(), digest])
    return _digest({"dataset": files, "provenance": provenance}), provenance[0][1]


def assert_source_current(review: DatasetReview) -> None:
    current, profile = source_identity(review.dataset_repo_id, {x.session_id for x in review.episodes})
    if (current, profile) != (review.source_sha256, review.profile_sha256):
        raise ValueError("Dataset or recording evidence changed; inspect --refresh and review again")


def read_review(repo_id: str) -> DatasetReview:
    path = preparation_path(repo_id)
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("review file exceeds the local size limit")
    review = DatasetReview.model_validate_json(path.read_text(encoding="utf-8"))
    if review.dataset_repo_id != repo_id:
        raise ValueError("review Dataset identity mismatch")
    return review


@contextmanager
def _locked(repo_id: str):
    directory = preparation_path(repo_id).parent
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / "review.lock"
    try:
        stream = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ValueError("another preparation operation owns this Dataset; retry after it finishes") from exc
    try:
        with stream:
            yield directory
    finally:
        lock.unlink()


def _write(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _archive(directory: Path) -> None:
    """Keep prior reviews/splits; refresh never replaces the only copy."""
    from lelab.episode_media import ensure_safe_dataset_path

    previous = [directory / name for name in ("review.json", "audit.json", "split.json")]
    previous = [path for path in previous if path.exists()]
    if previous:
        # Flat, short filenames avoid an extra deep directory on Windows copies.
        history = directory / "history"
        ensure_safe_dataset_path(evidence_root().absolute(), history)
        history.mkdir(parents=True, exist_ok=True)
        revision = uuid.uuid4().hex[:12]
        for path in previous:
            ensure_safe_dataset_path(evidence_root().absolute(), path, require_file=True)
            with (history / f"{revision}-{path.name}").open("xb") as stream:
                stream.write(path.read_bytes())


def inspect_dataset(repo_id: str, *, refresh: bool = False) -> dict:
    from tools.audit_dataset import audit
    from .color_sorting import local_split_manifest_path
    from lelab.episode_media import ensure_safe_dataset_path

    if (repo_id.split("/")[-1].startswith("color_sorting_v1")
            or local_split_manifest_path(evidence_root(), repo_id).exists()):
        raise ValueError("use the color-sorting task labels/split workflow for this task")
    with _locked(repo_id) as directory:
        if (directory / "review.json").exists() and not refresh:
            raise ValueError("review already exists; use status, or inspect --refresh to archive and re-review")
        sessions_before = set()
        for path in (evidence_root().absolute() / "sidecars").glob("*/frames.jsonl"):
            ensure_safe_dataset_path(evidence_root().absolute(), path, require_file=True)
            with path.open(encoding="utf-8") as stream:
                try:
                    first = json.loads(stream.readline())
                except (ValueError, UnicodeError):
                    continue
            if isinstance(first, dict) and first.get("dataset_repo_id") == repo_id:
                sessions_before.add(path.parent.name)
        try:
            before = source_identity(repo_id, sessions_before)
        except (OSError, ValueError):
            before = None  # The audit below supplies the specific failure.
        report = audit(repo_id, ["arm", "table_veiw"])
        mapping = (report.get("sidecar") or {}).get("saved_episode_mapping", {})
        if report["status"] == "PASS":
            sessions = {item["session_id"] for item in mapping.values()}
            source, profile = source_identity(repo_id, sessions)
            if before != (source, profile) or sessions_before != sessions:
                report["status"] = "FAIL"
                report["failures"].append("Dataset/provenance changed during preparation; retry when recording is idle")
        # Failed audits remain inspectable but cannot create a training admission.
        if report["status"] != "PASS":
            _archive(directory)
            _write(directory / "audit.json", report)
            if (directory / "review.json").exists():
                old = read_review(repo_id).model_copy(update={"audit_status": "FAIL"})
                _write(directory / "review.json", old.model_dump(mode="json"))
            (directory / "split.json").unlink(missing_ok=True)
            return report
        review = DatasetReview(
            dataset_repo_id=repo_id, source_sha256=source, profile_sha256=profile,
            audit_status="PASS", episodes=[
                EpisodeReview(episode_index=i, session_id=mapping[str(i)]["session_id"])
                for i in range(report["episodes"])
            ],
        )
        _archive(directory)
        _write(directory / "audit.json", report)
        _write(directory / "review.json", review.model_dump(mode="json"))
        (directory / "split.json").unlink(missing_ok=True)
        return report


def label_episode(repo_id: str, episode_index: int, **decision) -> DatasetReview:
    with _locked(repo_id) as directory:
        if (directory / "split.json").exists():
            raise ValueError("split is frozen; inspect --refresh to start a new review revision")
        review = read_review(repo_id)
        if type(episode_index) is not int or not 0 <= episode_index < len(review.episodes):
            raise ValueError("episode_index is the zero-based saved Dataset index")
        values = review.episodes[episode_index].model_dump()
        values.update(decision)
        if (values["episode_index"], values["session_id"]) != (
            episode_index, review.episodes[episode_index].session_id
        ):
            raise ValueError("review cannot change episode/session identity")
        review.episodes[episode_index] = EpisodeReview.model_validate(values)
        _archive(directory)
        _write(directory / "review.json", review.model_dump(mode="json"))
        return review


def build_prepared_split(review: DatasetReview, validation: set[str], test: set[str]) -> PreparedSplit:
    if review.audit_status != "PASS":
        raise ValueError("technical audit must pass before freezing a split")
    sessions = {x.session_id for x in review.episodes}
    if validation & test or not (validation | test) <= sessions:
        raise ValueError("validation/test sessions overlap or are unknown")
    if any(x.decision == "pending" for x in review.episodes):
        raise ValueError("review every saved episode before freezing")
    partitions = {"train": [], "validation": [], "test": []}
    excluded = []
    for item in review.episodes:
        partition = "test" if item.session_id in test else "validation" if item.session_id in validation else "train"
        if partition == "train" and not (
            item.decision == "keep" and item.outcome == "success" and item.intervention is False
        ):
            excluded.append(item.episode_index)
            continue
        partitions[partition].append(EpisodeIdentity(
            dataset_repo_id=review.dataset_repo_id, session_id=item.session_id, episode_index=item.episode_index,
        ))
    split = PreparedSplit(
        profile_sha256=review.profile_sha256, source_sha256=review.source_sha256, review=review,
        partitions=partitions, excluded_training_episodes=excluded,
        normalization_stats_source={"episode_indices": [x.episode_index for x in partitions["train"]]},
    )
    validate_split_manifest(split)
    return split


def validate_prepared_split(split: PreparedSplit) -> None:
    validate_split_manifest(split)
    expected = build_prepared_split(
        split.review, {x.session_id for x in split.partitions["validation"]},
        {x.session_id for x in split.partitions["test"]},
    )
    if expected != split:
        raise ValueError("frozen split does not match its human review/source identity")


def freeze_split(repo_id: str, validation: set[str], test: set[str]) -> PreparedSplit:
    with _locked(repo_id) as directory:
        if (directory / "split.json").exists():
            raise ValueError("split already frozen; existing jobs keep their original snapshot")
        review = read_review(repo_id)
        split = build_prepared_split(review, validation, test)
        assert_source_current(review)
        _write(directory / "split.json", split.model_dump(mode="json"))
        return split


def preparation_summary(repo_id: str) -> dict:
    """Small UI summary, never decode videos or assert current raw integrity here."""
    try:
        if not preparation_path(repo_id).exists():
            status = "AUDIT_FAILED" if preparation_path(repo_id, "audit.json").exists() else "NOT_REVIEWED"
            return {"status": status}
        review = read_review(repo_id)
        frozen = preparation_path(repo_id, "split.json")
        if frozen.exists():
            if frozen.stat().st_size > 8 * 1024 * 1024:
                raise ValueError("split exceeds size limit")
            split = PreparedSplit.model_validate_json(frozen.read_text(encoding="utf-8"))
            validate_prepared_split(split)
            if split.review != review:
                raise ValueError("split/review mismatch")
        return {
            "status": "AUDIT_FAILED" if review.audit_status == "FAIL" else "FROZEN" if frozen.exists() else "REVIEW_REQUIRED",
            "audit_status": review.audit_status,
            "episodes": len(review.episodes), "sessions": len({x.session_id for x in review.episodes}),
            "pending": sum(x.decision == "pending" for x in review.episodes),
            "excluded": sum(x.decision == "exclude" for x in review.episodes),
            "source_check": "required_at_training_start",
        }
    except (OSError, ValueError):
        return {"status": "INVALID_REVIEW"}
