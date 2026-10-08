"""Bind a frozen local task split to the official dataset factory.

No trainer, Dataset format or source data is replaced. The worker scopes official
datasets to admitted episodes and replaces only their in-memory statistics.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

from .color_sorting import SplitManifest, local_split_manifest_path, validate_split_manifest
from .data_preparation import (
    PreparedSplit, assert_source_current, preparation_path, read_review, validate_prepared_split,
)


def manifest_digest(manifest: SplitManifest) -> str:
    payload = json.dumps(manifest.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def parse_manifest(text: str) -> SplitManifest:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("split manifest must be a JSON object")
    if payload.get("schema_version") == "2.0":
        manifest = PreparedSplit.model_validate(payload)
        validate_prepared_split(manifest)
    else:
        manifest = SplitManifest.model_validate(payload)
        validate_split_manifest(manifest)
    return manifest


def read_manifest(path: Path, repo_id: str) -> SplitManifest:
    if path.is_symlink() or path.is_junction() or path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("split must be a bounded regular local file")
    manifest = parse_manifest(path.read_text(encoding="utf-8"))
    if manifest.partitions["train"][0].dataset_repo_id != repo_id:
        raise ValueError("split Dataset identity does not match the request")
    return manifest


def bind_request(request, *, source: Path | None = None):
    """Return a validated request + snapshot; never accept caller-supplied paths."""
    root = Path(os.environ.get("LELAB_RECORDING_EVIDENCE_ROOT", ".local/evidence/recordings"))
    color_path = local_split_manifest_path(root, request.dataset_repo_id)
    review_path = preparation_path(request.dataset_repo_id)
    prepared = request.dataset_task == "data_review_v1" or review_path.exists() or preparation_path(
        request.dataset_repo_id, "audit.json"
    ).exists()
    path = source or (preparation_path(request.dataset_repo_id, "split.json") if prepared else color_path)
    is_color_task = (
        request.dataset_task == "color_sorting_v1"
        or request.dataset_repo_id.split("/")[-1].startswith("color_sorting_v1")
        or color_path.is_file()
    )
    if not is_color_task and not prepared and source is None:
        return request, None
    if is_color_task and prepared:
        raise ValueError("conflicting task/review workflows; retain the color-sorting task split")
    if request.policy_type != "act" or request.dataset_image_transforms_enable:
        raise ValueError("reviewed datasets require ACT with image augmentation disabled")
    if not path.is_file():
        raise ValueError("Freeze the reviewed session split before training; pending or failed audits cannot train")
    manifest = read_manifest(path, request.dataset_repo_id)
    task = "data_review_v1" if isinstance(manifest, PreparedSplit) else "color_sorting_v1"
    if request.dataset_task is not None and request.dataset_task != task:
        raise ValueError("requested task conflicts with the frozen split")
    if isinstance(manifest, PreparedSplit):
        from lelab.episode_media import resolve_dataset_dir
        if source is None and read_review(request.dataset_repo_id) != manifest.review:
            raise ValueError("current review differs from the frozen split")
        if request.dataset_root is not None:
            if Path(request.dataset_root).resolve() != resolve_dataset_dir(request.dataset_repo_id).resolve():
                raise ValueError("custom Dataset root differs from the reviewed local source")
        assert_source_current(manifest.review)
    digest = manifest_digest(manifest)
    train = manifest.normalization_stats_source.episode_indices
    if request.dataset_episodes is not None and request.dataset_episodes != train:
        raise ValueError("requested episodes differ from the frozen training partition")
    if request.dataset_split_sha256 is not None and request.dataset_split_sha256 != digest:
        raise ValueError("frozen split differs from the original job")
    values = request.model_dump()
    validation = manifest.partitions["validation"]
    values.update(
        dataset_task=task, dataset_split_sha256=digest, dataset_episodes=train,
        dataset_eval_split=len(validation) / (len(train) + len(validation)),
    )
    if isinstance(manifest, PreparedSplit):
        values["dataset_root"] = str(resolve_dataset_dir(request.dataset_repo_id))
    return type(request).model_validate(values), manifest


def training_stats(root: Path, episodes: list[int]) -> dict:
    """Aggregate only selected official v3 per-episode statistics, read-only."""
    import numpy as np
    import pyarrow.dataset as arrow
    from lerobot.datasets.compute_stats import aggregate_stats
    from lerobot.utils.utils import unflatten_dict

    table = arrow.dataset(root / "meta/episodes", format="parquet").to_table(
        filter=arrow.field("episode_index").isin(episodes)
    )
    rows = table.to_pylist()
    if sorted(row["episode_index"] for row in rows) != sorted(episodes):
        raise ValueError("training episode statistics are missing or duplicated")
    stats = [
        unflatten_dict({
            key.removeprefix("stats/"): np.asarray(value)
            for key, value in row.items() if key.startswith("stats/")
        })
        for row in rows
    ]
    if any(not item or "action" not in item or "observation.state" not in item for item in stats):
        raise ValueError("official per-episode action/state statistics are required")
    for item in stats:
        for feature in item.values():
            if any(not np.isfinite(value).all() for value in feature.values()):
                raise ValueError("nonfinite training statistics")
    return aggregate_stats(stats)


def dataset_file_identity(meta, episodes: list[int]) -> list[dict]:
    """Bind relative files, not old-machine paths or just order-invariant stats."""
    root = Path(meta.root).resolve()
    paths = set((root / "meta").rglob("*.json")) | set((root / "meta").rglob("*.parquet"))
    for episode in episodes:
        paths.add(root / meta.get_data_file_path(episode))
        for key in meta.video_keys:
            paths.add(root / meta.get_video_file_path(episode, key))
    result = []
    for path in sorted(paths):
        relative = path.relative_to(root)
        cursor = root
        for part in relative.parts:
            cursor /= part
            if cursor.is_symlink() or cursor.is_junction():
                raise ValueError("dataset identity cannot traverse a linked path")
        if not path.resolve().is_relative_to(root):
            raise ValueError("dataset file escaped its owning root")
        before = path.stat()
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("dataset changed while its identity was being frozen")
        result.append({"path": relative.as_posix(), "bytes": after.st_size, "sha256": digest})
    return result


def install_dataset_factory(manifest: SplitManifest, receipt: Path) -> None:
    """Install the bounded factory adapter in this one worker before trainer import."""
    from lerobot.datasets import factory
    from lerobot.datasets.utils import serialize_dict

    make_dataset = factory.make_dataset
    validate_split_manifest(manifest)
    if isinstance(manifest, PreparedSplit):
        validate_prepared_split(manifest)
    train_ids = manifest.normalization_stats_source.episode_indices
    validation_ids = [item.episode_index for item in manifest.partitions["validation"]]
    repo_id = manifest.partitions["train"][0].dataset_repo_id

    def make_train_eval(cfg):
        if (
            cfg.dataset.repo_id != repo_id
            or cfg.dataset.episodes != train_ids
            or cfg.dataset.image_transforms.enable
            or cfg.dataset.streaming
            or cfg.dataset.use_imagenet_stats
            or cfg.dataset.eval_split != len(validation_ids) / (len(train_ids) + len(validation_ids))
            or cfg.policy.type != "act"
        ):
            raise ValueError("effective training config conflicts with the frozen session split")
        if isinstance(manifest, PreparedSplit):
            from lelab.episode_media import resolve_dataset_dir
            if cfg.dataset.root is not None and Path(cfg.dataset.root).resolve() != resolve_dataset_dir(repo_id).resolve():
                raise ValueError("effective Dataset root differs from the reviewed source")
            assert_source_current(manifest.review)
        train = make_dataset(cfg)
        validation_cfg = copy.deepcopy(cfg)
        validation_cfg.dataset.episodes = validation_ids
        validation = make_dataset(validation_cfg)
        stats = training_stats(Path(train.root), train_ids)
        train.meta.stats = copy.deepcopy(stats)
        validation.meta.stats = copy.deepcopy(stats)
        serialized = serialize_dict(stats)
        stats_digest = hashlib.sha256(json.dumps(serialized, sort_keys=True).encode()).hexdigest()
        payload = {
            "schema_version": "1.0",
            "dataset_repo_id": repo_id,
            "split_sha256": manifest_digest(manifest),
            "profile_sha256": manifest.profile_sha256,
            "train_episodes": train_ids,
            "validation_episodes": validation_ids,
            "validation_frequency_steps": cfg.eval_steps,
            "test_episodes_loaded": [],
            "normalization_stats_source": "train_episode_metadata",
            "normalization_stats_sha256": stats_digest,
            "normalization_stats": serialized,
            "dataset_files": dataset_file_identity(train.meta, train_ids + validation_ids),
            "effective_policy": {
                "type": cfg.policy.type,
                "chunk_size": cfg.policy.chunk_size,
                "n_action_steps": cfg.policy.n_action_steps,
            },
        }
        if isinstance(manifest, PreparedSplit):
            assert_source_current(manifest.review)
            payload["reviewed_source_sha256"] = manifest.source_sha256
        if receipt.exists():
            previous = json.loads(receipt.read_text(encoding="utf-8"))
            if previous != payload:
                raise ValueError("training dataset/statistics changed within the job")
        else:
            temporary = receipt.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            temporary.replace(receipt)
        return train, validation

    factory.make_train_eval_datasets = make_train_eval
