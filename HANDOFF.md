# HANDOFF — M1 complete; M2 blocked; M3 camera evidence partial

**Snapshot:** 2026-09-17. **Context Pack:** 1.0.0. **Software release:** not created.
This is the replaceable live state. Delivered history belongs in CHANGELOG; milestone status belongs in ROADMAP.

## Repository and boundary

| Field | Verified state |
|---|---|
| Execution root | `C:\Project\Physical_AI\Lerobot` with its own `.git` |
| Starting child state | No child Git; commands resolved to the parent until M0 isolation |
| Baseline | `main` at `81b43520ea711a8af7e73577b6c4e174135d43b9`, pushed to origin |
| Working branch | `codex/bootstrap-so101-lab`, tracking `origin/codex/bootstrap-so101-lab` |
| Delivered implementation commit | `b414480818c57d6a8d9ebfdf5a749da3b8e737dd` |
| Remote | `https://github.com/sgyliu8/LeRobot.git`; initially verified public, non-fork and empty |
| Parent reference | `C:\Project\Physical_AI`, branch `codex/m10-learning-resource-integration`, HEAD `14bff36d42d54dd351c59decbcbf4fca3286e257` |
| Parent exception | Local `.git/info/exclude` contains `/Lerobot/`; no parent tracked/index/worktree/branch/remote change |
| Parent M10 | Observed only; not resumed or modified |

## Milestone state

- **M0 COMPLETE:** T-GIT-01/02/03 PASS; independent repo, remote, baseline and parent isolation verified.
- **M1 COMPLETE:** fixed runtime, official LeLab UI, project lifecycle, no-device tests and tracked upstream patch verified.
- **M2 PARTIAL / BLOCKED:** host is `YANGHOME`; only one independent CH343 control-port candidate is visible, so two-arm role mapping cannot yet be established.
- **M3 PARTIAL:** wrist/front identity, simultaneous 60-second preview and official LeRobot camera smoke passed; physical replug/order test T-CAM-03 is `NOT_RUN`.
- **M4–M8 NOT_STARTED:** no motor connection, calibration, movement, data recording, replay, training or evaluation was attempted.

## Installed runtime

| Component | Resolved identity |
|---|---|
| Python | 3.12.13 in project `.venv` |
| uv | 0.12.4; 144 locked / 114 installed packages |
| LeLab | 0.1.0, pinned checkout `6091a45811ef926a06b9b3622a9ab69fefb8bb7b` plus `patches/lelab-6091a458-so101-lab.patch` |
| LeRobot | 0.6.0, resolved Git commit `30da8e687a6dfc617fcd94afc367ac7071c376ce` |
| Node/npm | v24.16.0 / 11.13.0 for the pinned shipped frontend build |
| Entry point | `lelab.scripts.lelab:main`; imports come from ignored `_vendor/lelab` and project `.venv` |

The user-home LeRobot `ports`, `saved_configs`, `robots`, `calibration/teleoperators/so_leader` and `calibration/robots/so_follower` paths were inspected and remain absent. No other cache or calibration was cleared or changed.

## Live service and UI

- `scripts/lab.ps1 start/status/logs/stop` owns one recorded process and never calls the broad upstream stop command.
- At snapshot: loopback service `http://127.0.0.1:8000/` is **running**, PID `21604`, `/health` is `ok`, `/lab-runtime-status` reports `hardware_mode=null`.
- The retained Codex in-app browser tab visibly shows the official LeLab home page with no robot selected, no dataset selected, zero local jobs and Hugging Face not configured.
- Start, repeated start, status, logs, idle stop, restart and foreign-port refusal passed. Software stop is not a torque-off claim.
- Live boundary checks: allowed health 200; untrusted Host 400; untrusted Origin write 403; untrusted WebSocket rejected HTTP 403.

## Device and camera evidence

- Host: Windows 11 Pro 10.0.26200, i5-12450H, 15.78 GiB RAM, Intel UHD. Current free disk after build is approximately 50.66 GiB.
- Serial/PnP: COM1 is ACPI legacy and excluded. COM6 is one CH343 USB candidate, unopened and role unknown. COM7 shares the front camera's composite USB container and is not admitted as a robot endpoint. No serial port was opened.
- Camera mapping: `wrist = LRCP G720P / DSHOW index 1`; `front = 1080P USB Camera / DSHOW index 2`. `UGREEN Camera 2K / index 0` was left unopened.
- Simultaneous 60-second 640×480/15 fps probe: wrist 902 frames / 15.012 fps; front 1788 frames / 29.816 fps; both 0 read failures, 0 invalid shapes and monotonic arrival timestamps.
- Official LeRobot `OpenCVCamera` then read five RGB `480×640×3 uint8` frames from each mapped camera and disconnected, proving preview-to-driver handle handoff in camera-only scope.
- Raw frames, full instance IDs, local logs, PID state and camera metrics remain under ignored `.local/`; none are in Git or uploaded.

## Verification ledger

| Check | Result |
|---|---|
| `python -X utf8 tools/validate_pack.py` | PASS: `PACK_STATIC_PASS` |
| `uv lock --check` / `uv pip check` | PASS |
| Main environment unittest discovery | PASS: 24/24 |
| Separate `.venv-rebuild` from lock | PASS: 114 packages, imports/entrypoint, compatibility and then-current 23 tests; temporary environment removed |
| Clean pinned patch forward / runtime reverse apply | PASS |
| Frontend scoped ESLint / Vitest / production build | PASS / 6 of 6 / PASS |
| Full upstream frontend lint | FAIL: 6 errors and 13 warnings in untouched upstream files |
| npm dependency audit | OPEN: 1 high and 2 moderate; no automatic dependency-changing fix applied |
| Real UI browser smoke and service restart | PASS |
| T-DEV-01 two independent arm endpoints | BLOCKED: only one plausible controller port present |
| T-CAM-01 / 02 / 04 | PASS within camera-only scope |
| T-CAM-03 replug/order stability | NOT_RUN |
| Robot connect / calibration / teleoperation / record / replay / inference | NOT_RUN |

## Implemented files and behavior

- `pyproject.toml`, `.python-version`, `uv.lock`, `configs/upstream-pins.json`: fixed environment identity.
- `tools/bootstrap_upstream.ps1`: exact checkout, idempotent patch, `npm ci` and shipped frontend build.
- `patches/lelab-6091a458-so101-lab.patch`: atomic cross-mode owner, positive motion-target propagation, honest mixed-unit/stale telemetry, and loopback request boundary.
- `scripts/lab.ps1`: project-owned lifecycle with exact PID/start/executable/command-line checks.
- `tests/test_runtime_contracts.py`: no-device regression for UI health, boundary, ownership, limits and telemetry.
- README, dependency contract, ADR, ROADMAP, CHANGELOG and this HANDOFF were updated in their owning roles.

## Blockers and next ready action

1. M2 needs an attended physical USB differential: identify why only one CH343 endpoint is present, then map two independent controller ports to leader/follower without opening them as a probe.
2. M3 completion needs one controlled camera replug/order check to prove the local name-to-index mapping fails closed rather than silently swapping roles.
3. Before any M4 C/D action, obtain one consolidated bench confirmation: exact kit/motor and both power-supply output labels, stable mounting and starting pose, owner present, an independent physical stop method, and the approved mode/task/range. `Robot.connect()`, calibration and motion remain prohibited until then.

No merge, release, tag, public deployment, cloud job, Hub upload, model download, driver install or independent external review occurred. The review mode was one agent applying multiple checklists, not five independent experts.
