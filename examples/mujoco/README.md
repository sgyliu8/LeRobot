# SO101 recorded-episode playback

This example maps one existing LeRobot Dataset v3 episode into the pinned
RobotStudio SO101 model from MuJoCo Menagerie. It reads `observation.state`
without decoding camera video or constructing robot/camera drivers.

```powershell
.\examples\mujoco\bootstrap_model.ps1
uv sync --project .\examples\mujoco --frozen
uv run --project .\examples\mujoco --frozen -- `
  python .\examples\mujoco\replay_episode.py `
  --dataset-id local/my_dataset `
  --profile .\.local\recording-profiles\my_dataset.json `
  --episode 0 `
  --report .\.local\evidence\mujoco-episode-0.json `
  --trajectory-jsonl .\.local\ros2\episode-0.jsonl
```

The reader is offline-only: it requires a complete existing Dataset v3 tree,
sets the Hub/Datasets offline flags, disables video download, and refuses to
write derived files inside the source Dataset. Pass `--dataset-root` when the
Dataset is outside the standard local LeRobot cache. Existing reports are not
overwritten unless `--overwrite` is explicit.

The required frozen profile must match the Dataset id, FPS, action semantics,
and exact mixed joint units. Add `--viewer` for the native interactive viewer.
Range violations fail by default; `--clip` is an explicit, reported
visualization choice. The first five joints map degrees to radians. The
recorded gripper value is normalized 0–100 rather than a metric opening and is
therefore rendered as a visual-only numeric degree sweep.

The trajectory is published atomically only after every expected frame is
written. Each row carries the Dataset id, episode, contiguous frame index,
expected frame count, source-array digest, and any range transform. The ROS
reader rejects a partial or mixed-identity file. Reports distinguish the digest
of the source episode arrays from the digest of the derived JSONL bytes.

Run the isolated checks with:

```powershell
uv run --project .\examples\mujoco --frozen --group dev `
  python -m pytest -q .\examples\mujoco\test_replay_episode.py
```

Passing this experiment proves only that recorded states drove a fixed model
through forward kinematics. It does not establish dynamics, collision safety,
grasp success, sim-to-real transfer, physical zero/sign registration, or
real-robot behavior. A completed viewer event loop is not by itself a human
visual inspection.
