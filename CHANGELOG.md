# Changelog

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
