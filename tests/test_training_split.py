"""Synthetic v3 media + official parser/loader; no policy training or hardware."""
from __future__ import annotations

import json

import numpy as np
import pytest

from so101_lab.color_sorting import SplitManifest, local_split_manifest_path
from so101_lab.training_split import bind_request, install_dataset_factory, manifest_digest


def manifest(repo_id="fixture/color_sorting_v1"):
    return SplitManifest.model_validate({
        "profile_sha256": "a" * 64,
        "partitions": {
            name: [{"dataset_repo_id": repo_id, "session_id": name, "episode_index": index}]
            for index, name in enumerate(("train", "validation", "test"))
        },
        "normalization_stats_source": {"partition": "train", "episode_indices": [0]},
    })


@pytest.fixture(autouse=True)
def no_hardware(monkeypatch):
    import serial
    import cv2
    import lerobot.robots
    import lerobot.teleoperators

    def forbidden(*args, **kwargs):
        pytest.fail("actual device constructor reached")

    monkeypatch.setattr(serial, "Serial", forbidden)
    monkeypatch.setattr(cv2, "VideoCapture", forbidden)
    monkeypatch.setattr(lerobot.robots, "make_robot_from_config", forbidden)
    monkeypatch.setattr(lerobot.teleoperators, "make_teleoperator_from_config", forbidden)
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("HF_DATASETS_OFFLINE", "1")


def test_task_binding_is_strict_and_never_silently_uses_all_data(tmp_path, monkeypatch):
    from lelab.train import TrainingRequest, build_training_command

    monkeypatch.setenv("LELAB_RECORDING_EVIDENCE_ROOT", str(tmp_path))
    request = TrainingRequest(dataset_repo_id="fixture/color_sorting_v1", dataset_task="color_sorting_v1")
    with pytest.raises(ValueError, match="Freeze"):
        bind_request(request)
    path = local_split_manifest_path(tmp_path, request.dataset_repo_id)
    path.parent.mkdir()
    path.write_text(manifest().model_dump_json(), encoding="utf-8")
    bound, split = bind_request(request)
    assert bound.dataset_episodes == [0]
    assert bound.dataset_split_sha256 == manifest_digest(split)
    assert "--dataset.use_imagenet_stats" in build_training_command(bound, "fixture-output")
    with pytest.raises(ValueError, match="differ"):
        bind_request(request.model_copy(update={"dataset_episodes": [0, 1]}))
    with pytest.raises(ValueError, match="augmentation"):
        bind_request(request.model_copy(update={"dataset_image_transforms_enable": True}))
    for episodes in ([], [0, 0], [True], [-1], [1.5], ["1"]):
        with pytest.raises(ValueError):
            TrainingRequest(dataset_repo_id="fixture/demo", dataset_episodes=episodes)


def test_official_video_loader_uses_separate_split_and_train_only_statistics(tmp_path, monkeypatch):
    import draccus
    import torch
    from lelab.train import TrainingRequest, build_training_command
    from lerobot.configs.train import TrainPipelineConfig
    from lerobot.datasets import factory
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.configs.video import RGBEncoderConfig
    import lerobot.policies.act.configuration_act  # noqa: F401

    dataset_root = tmp_path / "dataset"
    features = {
        name: {"dtype": "float32", "shape": (6,), "names": [f"joint_{i}" for i in range(6)]}
        for name in ("action", "observation.state")
    }
    features.update({
        f"observation.images.{key}": {"dtype": "video", "shape": (32, 32, 3), "names": ["height", "width", "channels"]}
        for key in ("arm", "table_veiw")
    })
    encoder = RGBEncoderConfig(vcodec="h264", pix_fmt="yuv420p", crf=23, g=2)
    ds = LeRobotDataset.create(
        "fixture/color_sorting_v1", fps=15, root=dataset_root, features=features,
        use_videos=True, rgb_encoder=encoder, streaming_encoding=True,
        image_writer_processes=0, image_writer_threads=0,
    )
    for episode, offset in enumerate((0, 100, 1000)):
        for frame in range(3):
            ds.add_frame({
                "action": np.full(6, offset + frame, dtype=np.float32),
                "observation.state": np.full(6, offset + frame, dtype=np.float32),
                "observation.images.arm": np.full((32, 32, 3), 40 + episode, dtype=np.uint8),
                "observation.images.table_veiw": np.full((32, 32, 3), 150 + episode, dtype=np.uint8),
                "task": "synthetic fixture only",
            })
        ds.save_episode(parallel_encoding=False)
    ds.finalize()
    before_stats = (dataset_root / "meta/stats.json").read_bytes()
    request = TrainingRequest(
        dataset_repo_id="fixture/color_sorting_v1", dataset_root=str(dataset_root),
        dataset_task="color_sorting_v1", dataset_episodes=[0],
        dataset_eval_split=0.5, eval_steps=1,
        policy_chunk_size=2, policy_n_action_steps=1, num_workers=0,
    )
    cmd = build_training_command(request, str(tmp_path / "run"))
    cfg = draccus.parse(TrainPipelineConfig, args=cmd[3:])
    cfg.validate()
    assert cfg.eval_steps == 1
    seen = []
    original = factory.make_dataset
    def tracked(config):
        seen.append(config.dataset.episodes)
        return original(config)
    monkeypatch.setattr(factory, "make_dataset", tracked)
    monkeypatch.setattr(factory, "make_train_eval_datasets", factory.make_train_eval_datasets)
    receipt = tmp_path / "receipt.json"
    install_dataset_factory(manifest(), receipt)
    train, validation = factory.make_train_eval_datasets(cfg)
    assert seen == [[0], [1]]
    assert train.episodes == [0] and validation.episodes == [1]
    np.testing.assert_allclose(train.meta.stats["action"]["mean"], np.ones(6))
    np.testing.assert_allclose(validation.meta.stats["action"]["mean"], np.ones(6))
    assert (dataset_root / "meta/stats.json").read_bytes() == before_stats
    batch = next(iter(torch.utils.data.DataLoader(train, batch_size=1, num_workers=0)))
    assert set(("action", "observation.images.arm", "observation.images.table_veiw")) <= set(batch)
    assert int(validation[0]["episode_index"]) == 1
    payload = json.loads(receipt.read_text())
    assert payload["train_episodes"] == [0]
    assert payload["test_episodes_loaded"] == []
    assert payload["effective_policy"]["chunk_size"] == 2
    assert payload["normalization_stats_sha256"]
    assert any(item["path"].endswith(".mp4") for item in payload["dataset_files"])
    import pyarrow.parquet as parquet
    import pyarrow as arrow
    data_file = dataset_root / train.meta.get_data_file_path(0)
    table = parquet.read_table(data_file)
    actions = table.column("action").to_pylist()
    actions[0], actions[2] = actions[2], actions[0]
    changed = table.set_column(
        table.schema.get_field_index("action"), table.schema.field("action"),
        arrow.array(actions, type=table.schema.field("action").type),
    )
    parquet.write_table(changed, data_file)
    with pytest.raises(ValueError, match="changed within"):
        factory.make_train_eval_datasets(cfg)
    cfg.dataset.image_transforms.enable = True
    with pytest.raises(ValueError, match="conflicts"):
        factory.make_train_eval_datasets(cfg)


def test_legacy_manifest_cannot_invent_success_admission(tmp_path):
    from so101_lab.training_split import read_manifest

    legacy = manifest().model_dump(mode="json")
    legacy["schema_version"] = "1.0"
    legacy.pop("training_inclusion")
    legacy.pop("excluded_training_episodes")
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy))
    with pytest.raises(ValueError):
        read_manifest(path, "fixture/color_sorting_v1")
