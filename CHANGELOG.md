# Changelog

## Unreleased — M5 software-ready recording/data closure — 2026-09-18

- Reconciled the live Yang101 state: distinct CH343 COM5 leader and COM6 follower, completed user calibration/teleoperation, and preserved `arm` wrist plus `table_veiw` front roles. Backed up the existing robot configuration, port records and both calibration files without recalibration or motion.
- Replaced mode-string ownership with unique leases and session-scoped controls; delayed old cleanup can no longer release a newer task. Calibration/teleoperation HTTP and WebSocket status now consume worker-owned telemetry caches instead of reading the serial bus.
- Split recording termination into explicit Accept, finite Timeout, destructive Discard and Stop semantics. Stop fences further command dispatch, never enters reset/next episode, and preserves a non-empty interrupted episode; only Discard clears the current buffer.
- Connected the saved UI profile to the actual runtime request for Dataset FPS, typed camera settings, H.264/yuv420p/PyAV encoding and exact finite positive six-key SO101 target-delta limits with correct mixed units.
- Preserved official LeRobot Dataset v3 `action` label semantics while adding ignored per-frame evidence for requested/to-send/effective-sent targets, clipping, pre-command state, nominal dataset time and measured host loop/camera timing.
- Added local-only single-name canonicalisation, exact-ID/profile-locked resume, read-only dataset browse/audit, and short-video EOF handling that no longer substitutes the last physical frame.
- Added an atomic shutdown fence and exact Windows process/listener revalidation; software stop remains explicitly distinct from physical torque-off.
- Added M5 runtime and data-integrity regressions plus a strict read-only dataset auditor. The 54 project tests, 268 pinned-LeLab tests, 15 frontend tests, production build and a clean pinned-patch apply/test/build/import passed.
- Made unload-time teleoperation stops truth-preserving: the UI retains the exact session token and reports a clean disconnect only after cached exact-session status confirms it. Recording receipts now show the resolved camera backend/index/shape/capture rate plus every target-delta value and unit.
- Hardened packed-video browsing: resume requires Parquet rows and exactly matching decoded frames for every indexed episode/camera, and both the active and secondary all-camera players clamp to their own episode windows.
- Reconfirmed both configured cameras through pinned LeRobot at 640×480/30 with increasing host timestamps and clean handle release. The in-app browser lacks `navigator.mediaDevices`, so its failed modal thumbnails remain `NOT_RUN` for UI preview rather than being treated as a physical-camera failure or pass.
- Completed a synthetic H.264/Parquet Dataset v3 path from one episode/finalize through official loader and CPU DataLoader, then exact-ID resume to three episodes. This is software evidence only: the real dataset ID, three attended episodes and current two-camera media audit remain `NOT_RUN`.

No real recording, replay, inference, training, Hub upload, cloud job, merge, release, tag or public deployment occurred. The fixed LeLab/LeRobot revisions and locked dependency set were retained. The final tracked vendor patch SHA-256 is `e5032c005b8264a9138aaa86cb433dbca7a694d933fe33e528802cc91a9c4664`.

## Unreleased — M0/M1 runtime candidate and M2/M3 observation — 2026-09-17

- Established the independent child Git repository, pushed the clean `main` baseline, and created `codex/bootstrap-so101-lab`; the only parent-side change is local `/Lerobot/` exclusion metadata.
- Locked Python 3.12.13, LeLab `6091a458…`, LeRobot v0.6.0 / `30da8e68…`, and 114 resolved packages in `uv.lock`; added a reproducible pinned checkout/frontend bootstrap.
- Added a minimal tracked LeLab patch for cross-mode ownership, request boundaries, motion-limit propagation, and honest telemetry state/units, with no-device regression tests and a rebuildable editable checkout.
- Added project-owned loopback start/status/logs/stop commands with exact process identity, foreign-port refusal, and idle-only software stop.
- Verified the real LeLab page in a local browser, live hostile Host/Origin/WS rejection, clean-environment rebuild, frontend tests/build, and 24 Python tests.
- Re-enumerated `YANGHOME`: one CH343 control-port candidate is present but a second independent arm endpoint is not. No serial port or robot was opened.
- Mapped wrist/front cameras, passed a 60-second simultaneous DSHOW probe and official LeRobot camera smoke, and kept frames, full identifiers, logs, and metrics local-only. Replug/order validation remains `NOT_RUN`.

No `Robot.connect()`, calibration, teleoperation, recording, replay, inference, model download, training, upload, merge, release, or public deployment occurred.

## Context Pack 1.0.0 — 2026-09-17

Delivered the SO101 integration project contracts, upstream-first architecture, nested-repository policy, phased roadmap, UI interaction specification, mixed-unit data contracts, bench-session permissions, proportionate test/CI strategy, research source register, five-role three-round review summary, startup/resume prompts and offline pack validator.

Verified through read-only MCP: child directory and parent Git boundary; target repository metadata/empty branch list; current host and OS-level device enumeration. Reviewed selected official LeLab/LeRobot source paths, Hugging Face/Seeed/OpenAI/Git/uv documentation and bounded paper abstracts.

Corrected planning risks: guessed COM ports; parent-repository capture; stale calibration cache names; assuming `connect()` is read-only; treating normalised gripper positions as joint angles; equating data browsing with actuator replay; treating screen automation as safety supervision.

**Not delivered:** installed robot runtime, automatic installer, custom control UI, hardware driver, physical calibration, motion validation, training or safety certification.
No parent project file or target GitHub repository was changed by the preparation session.
