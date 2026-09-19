# Front-camera geometry experiment

This is the next offline experiment after recorded-episode playback. It is not
a robot-control path. The first result is a measured camera/plane transform and
an image overlay with held-out reprojection error.

## Inputs that must be measured

1. Keep the front camera and table fixed.
2. Print or mount one ChArUco board and measure its square and marker sizes.
3. Capture calibration images across the working area; keep a separate holdout
   set that is not used for fitting.
4. Save the camera intrinsics for the exact resolution and focus setting.
5. Establish a measured base-to-board transform. Do not substitute an identity
   transform when this measurement is missing.

Copy `config.example.json` into ignored `.local/vision_geometry/config.json`
and replace every `null` measurement. Camera intrinsics, camera-to-board PnP,
base-to-camera composition, TCP calibration, joint calibration, and timestamp
alignment remain separate artifacts.

## Acceptance evidence

- board dimensions and image resolution are recorded with units;
- fit and holdout image sets are disjoint;
- per-image and aggregate reprojection error are reported in pixels;
- the base-frame table point is overlaid on held-out images;
- uncertainty, occlusion, and out-of-plane assumptions are stated;
- no serial port, robot driver, controller topic, replay, or inference is
  opened by the experiment.

Two RGB cameras are not treated as calibrated stereo merely because both are
connected. A future pixel-to-target proposal must remain visual-only until the
camera, base, TCP, joint, and clock transforms are independently established.

**Current status:** `NOT_RUN`. Board dimensions, intrinsics, extrinsics, and a
new attended image set have not been supplied for this experiment.
