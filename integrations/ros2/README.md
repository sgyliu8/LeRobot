# ROS 2 read-only playback

This integration publishes only `/clock` and `/joint_states` from an ignored,
local trajectory. `robot_state_publisher` owns `/tf` and `/tf_static`. Nothing
imports a LeRobot robot, camera, or serial driver, and no controller or command
topic is published.

## 1. Prepare local inputs

Generate a trajectory with the [MuJoCo playback](../../examples/mujoco/README.md).
The atomically published JSONL preserves source `.pos` feature names, mixed
source units, explicit model joint names, Dataset nominal timestamps, exact
episode identity, expected frame count, source digest, and transform
provenance. The reader rejects partial or mixed-identity trajectories.

Prepare a local-only ROS description package from the pinned UI assets:

```powershell
uv run --frozen python .\integrations\ros2\prepare_description.py
```

The generated package is under ignored `.local/ros2_ws/src`. This avoids the
upstream package's stale install path without editing or redistributing its
mesh assets.

Before ROS is involved, audit the recorded positions against the URDF limits:

```powershell
uv run --frozen python .\integrations\ros2\joint_state_replay.py `
  --trajectory .\.local\ros2\episode-0.jsonl `
  --urdf .\_vendor\lelab\frontend\public\so-101-urdf\urdf\so101_new_calib.urdf `
  --audit-only --report .\.local\ros2\limit-audit.json
```

Limit violations block publication by default. `--clip-urdf` creates an
explicitly marked visual derivative; it never rewrites the Dataset trajectory.
Values no more than `1e-6 rad` outside an XML limit are treated as serialization
rounding and boundary-adjusted with a separate count. Larger violations remain
blocked unless clipping is explicit. Reports stay under `.local` and are never
overwritten without `--overwrite-report`.

## 2. Build the description package

Use an existing Ubuntu 24.04 / ROS 2 Jazzy installation. Do not install ROS
into the LeLab Python environment.

```bash
cd /mnt/c/path/to/Lerobot/.local/ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
export ROS_DOMAIN_ID=101
```

## 3. Start consumers before playback

Use four terminals, source the same ROS and workspace setup in every terminal,
and set the same `ROS_DOMAIN_ID=101`.

Terminal A — TF source:

```bash
ros2 run robot_state_publisher robot_state_publisher \
  "$(ros2 pkg prefix --share so_arm_description)/urdf/so101_new_calib.urdf" \
  --ros-args -p use_sim_time:=true
```

Terminal B — RViz:

```bash
rviz2 -d /mnt/c/path/to/Lerobot/integrations/ros2/so101.rviz \
  --ros-args -p use_sim_time:=true
```

Terminal C — start recording before the first frame:

```bash
ros2 bag record /clock /joint_states /tf /tf_static
```

Do not add `--use-sim-time` to this recorder command. The bag uses host receipt
time so the transient-local `/tf_static` sample published before the first
`/clock` is not discarded. `/clock` and the JointState/TF headers still carry
the Dataset nominal timeline; robot_state_publisher and RViz continue to use
simulation time.

Terminal D — publish once, last:

```bash
python /mnt/c/path/to/Lerobot/integrations/ros2/joint_state_replay.py \
  --trajectory /mnt/c/path/to/Lerobot/.local/ros2/episode-0.jsonl \
  --urdf "$(ros2 pkg prefix --share so_arm_description)/urdf/so101_new_calib.urdf" \
  --clip-urdf
```

The publisher waits for subscribers on both topics before frame zero and
flushes after the last frame. A successful animation or bag proves only
message, nominal-time, URDF, and TF plumbing. It is not live feedback, motor
control, dynamics validation, collision safety, or task success.

After recording, require `ros2 bag info <bag>` to show nonzero counts for
`/clock`, `/joint_states`, `/tf`, and `/tf_static`; preserve that output beside
the local report. The report records `ROS_DOMAIN_ID`, speed, readiness timeout,
and publisher wall time. Joint zero/sign conventions are inherited from fixed
sources; registration against the physical arm remains a separate experiment.

**Current host status:** source, trajectory validation, package preparation,
and limit auditing can run without ROS. JointState, TF, RViz, and rosbag2 remain
`NOT_RUN` until an existing ROS 2 environment is available.
