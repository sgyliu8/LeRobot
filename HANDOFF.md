# HANDOFF — M5 software ready; attended three-episode capture pending

**Snapshot:** 2026-09-18. **Context Pack:** 1.0.0. **Software release:** not created.
This is the replaceable live state. Delivered history belongs in CHANGELOG; milestone status belongs in ROADMAP.

## Repository and boundary

| Field | Verified state |
|---|---|
| Execution root | `C:\Project\Physical_AI\Lerobot` with its own `.git` |
| Session starting HEAD | `523a0b6dcea8581c54d320245eac50bb27414ed4` |
| Working branch | `codex/bootstrap-so101-lab`, tracking `origin/codex/bootstrap-so101-lab` |
| Live commit | Use `git rev-parse HEAD`; this file cannot contain the hash of the commit that contains itself |
| Remote | `https://github.com/sgyliu8/LeRobot.git` |
| Parent reference | `C:\Project\Physical_AI`, branch `codex/m10-learning-resource-integration`, HEAD `14bff36d42d54dd351c59decbcbf4fca3286e257` |
| Parent exception | Local parent `.git/info/exclude` already contains `/Lerobot/`; no parent tracked/index/worktree/branch/remote change in this session |
| Parent M10 | Observed only; not resumed or modified |

The inherited untracked `docs/reviews/M5_REVIEW_AND_PLAN.md` remains preserved and is not silently staged. The requested `docs/reviews/M5_REVIEW_INPUT.md` was not present; the existing review supplied the corresponding finding set.

## Milestone state

- **M0 COMPLETE:** independent child Git root, target remote and parent isolation remain verified.
- **M1 COMPLETE:** fixed runtime, official LeLab UI, project lifecycle, no-device tests and tracked upstream patch remain reproducible.
- **M2 COMPLETE:** current Windows PnP has two distinct CH343 controllers; successful local operation maps COM5 to leader and COM6 to follower. COM1 remains legacy ACPI and COM7 remains part of a camera composite device.
- **M3 PARTIAL:** saved robot configuration maps `arm` to the wrist camera and the intentionally retained key `table_veiw` to the front camera. Both passed a fresh pinned-LeRobot 640×480/30 camera-only read with increasing host timestamps and clean release. T-CAM-03 replug/order stability is still `NOT_RUN`; the current recording-modal thumbnails did not render in the in-app browser, so this session does not claim a UI-preview pass.
- **M4 PARTIAL:** the user completed Yang101 leader/follower calibration and COM5→COM6 teleoperation; existing local logs and calibration files corroborate the workflow. This session backed them up and did not recalibrate or move either arm. The next recording session still requires one current attended-bench confirmation.
- **M5 SOFTWARE_READY / AWAITING_ATTENDED_CAPTURE:** the software/data path is repaired and synthetic end-to-end tests pass. Real dataset ID and real episode count remain `NOT_RUN`/0; M5 is not complete.
- **M6–M8 NOT_STARTED:** no training, replay, inference, evaluation, ROS 2, simulation or VLA work was started.

## Installed runtime

| Component | Resolved identity |
|---|---|
| Python | 3.12.13 in project `.venv` |
| uv | locked environment; 144 resolved / 114 installed packages |
| LeLab | 0.1.0, pinned checkout `6091a45811ef926a06b9b3622a9ab69fefb8bb7b` plus `patches/lelab-6091a458-so101-lab.patch` |
| LeRobot | 0.6.0, resolved Git commit `30da8e687a6dfc617fcd94afc367ac7071c376ce` |
| Entry point | `lelab.scripts.lelab:main`; imports resolve from ignored `_vendor/lelab` and the project `.venv` |

No dependency was upgraded, no second LeRobot/Seeed fork was introduced, and nothing was installed into the parent environment or global Python.

## M5 software result

- Recording control now treats **Accept**, **Timeout**, **Discard**, and **Stop** as different events. Timeout is finite; Discard is the only clear-and-rerecord action; Stop never enters reset/next episode and preserves a non-empty interrupted episode.
- Every hardware mode has a unique lease/session. Delayed old cleanup or HTTP controls cannot release or control a newer same-mode task. Calibration and teleoperation HTTP/WS status read worker-owned caches rather than reopening the serial path.
- The UI recording profile is the request source for Dataset FPS, two camera configs, H.264/PyAV encoding and the exact six SO101 joint-limit keys. Values must be finite and positive; the first five keys use degrees and `gripper` uses `normalized_0_100`. These target-delta limits are not speed, collision or safety guarantees.
- Dataset v3 retains the official processed operator target as `action`. An ignored local trace separately records requested/processed target, command target, effective sent target, clipping, pre-command measured state, nominal dataset time and host loop/camera timing.
- Local single-component dataset names become `local/<name>`, `push_to_hub` is fixed false, and resume requires the exact first returned ID plus an identical frozen profile.
- Browse, dataset-info and `tools/audit_dataset.py` are read-only. A short video request beyond physical EOF returns missing/error instead of substituting its last frame.
- The lifecycle stop path acquires an atomic shutdown fence and then revalidates the recorded process identity before stopping. It is a software-process fence, not a physical torque-off guarantee.

The candidate visible in the UI is Dataset 15 Hz, camera requests at their saved 640×480/30 fps values, H.264/yuv420p/PyAV CRF 23 and GOP 2. It is **not frozen for a real dataset yet** because the task and six limit values still require the attended-session confirmation.

## Live service and UI

- The project-owned LeLab service is available only on `http://127.0.0.1:8000/`; use `scripts/lab.ps1 status` for the current PID, health and hardware owner.
- The real page shows Yang101, local-only/no-HF-login recording wording, Dataset FPS and encoder controls, both camera keys, six joint-limit inputs with units, and separate Accept/Discard/Stop behavior. Start Recording remains disabled until a complete valid profile is supplied.
- `/lab-runtime-status` was idle (`hardware_mode=null`) after inspection. No Calibrate, Teleoperate, Record, Replay or Inference button was invoked in this session.
- Current `/available-cameras` enumerates UGREEN Camera 2K plus the two configured USB cameras. The configured cameras each passed ten 640×480/30 frames through pinned LeRobot `OpenCVCamera`, with available strictly increasing host timestamps, then disconnected. Recording-modal thumbnails still failed because the in-app verification browser exposes no `navigator.mediaDevices`; this is explicitly not counted as a UI-preview pass.

## Verification ledger

| Check | Result |
|---|---|
| `python -X utf8 tools/validate_pack.py` | PASS: `PACK_STATIC_PASS` |
| `uv lock --check` / `uv pip check` | PASS |
| Main Python regression discovery | PASS: 54/54 |
| M5 focused runtime/data regression | PASS: 30/30 |
| Full pinned-LeLab Python suite | PASS: 268/268 |
| Synthetic Dataset v3 new/finalize/loader/CPU DataLoader/resume-to-3 | PASS; fixture evidence only |
| True two-frame H.264 EOF boundary | PASS; past EOF returns missing |
| Frontend Vitest | PASS: 15/15 |
| Scoped frontend ESLint | PASS |
| Frontend production build | PASS |
| Clean pinned patch apply at `6091a458`, 44-file content match, actual import, Python tests, frontend tests/build | PASS; patch SHA-256 `e5032c005b8264a9138aaa86cb433dbca7a694d933fe33e528802cc91a9c4664` |
| Full upstream frontend lint | FAIL: 6 errors / 13 warnings in unrelated upstream files |
| npm audit | OPEN: 1 high / 2 moderate development-dependency findings; no forced upgrade |
| Real three-episode dataset, current two-view media and task result | NOT_RUN |
| Replay / training / inference | NOT_RUN |

Synthetic media and Parquet prove the software route only. A green page, HTTP 200 or test fixture is not hardware isolation or real-data acceptance evidence.

## Local-only evidence and privacy

- Pre-change robot config, ports and both Yang101 calibration files were copied to `.local/backups/m5-prechange-20260918-001956`; all five backup hashes matched their sources.
- Logs, device identifiers, recording profiles/traces, synthetic fixtures, fresh-apply checkout and future real videos/Parquet stay under ignored local roots or the official local LeRobot cache. None are staged or uploaded.
- No HF login, Hub upload, cloud job, W&B, public deployment or model download occurred.

## Blocker and next ready action

Before the first real recording, obtain one consolidated confirmation of: the exact simple task and success rule; the owner being physically present; unchanged secure mounting and correct power; the normal UI Stop plus independent physical power-cut method; the finite one-episode-then-two scope; and the six approved per-joint target-delta limits. The owner moves the leader; Codex only operates the existing UI, status and data checks.

Then record one new 20–30 s episode, finalize, audit both real videos/Parquet/action/timing, load it with official LeRobot and one CPU DataLoader batch, and resume the exact returned dataset ID for two more episodes without changing the profile. Only a verified total of three real episodes permits `M5_COMPLETE` and creates the M6 input.

No merge, release, tag, public deployment, hardware replay or policy run is authorised. Three actual independent reviewers performed the post-fix read-only domain checks; only the primary agent edited code and operated the local service.
