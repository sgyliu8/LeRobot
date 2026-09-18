# M5 integrated implementation review

**Date:** 2026-09-18

**Candidate:** `codex/bootstrap-so101-lab`, starting child HEAD `523a0b6dcea8581c54d320245eac50bb27414ed4`

**Pinned upstreams:** LeLab `6091a45811ef926a06b9b3622a9ab69fefb8bb7b`; LeRobot `30da8e687a6dfc617fcd94afc367ac7071c376ce`

**Tracked patch SHA-256:** `e5032c005b8264a9138aaa86cb433dbca7a694d933fe33e528802cc91a9c4664`

The requested `docs/reviews/M5_REVIEW_INPUT.md` was absent. The owner-provided task attachment and the preserved, inherited untracked `M5_REVIEW_AND_PLAN.md` supplied the reproduced finding set. This file is the consolidated tracked closeout; live milestone state remains authoritative in `HANDOFF.md` and `docs/ROADMAP.md`.

## Review independence and edit boundary

Three actual Codex subagents reviewed the same working candidate read-only. They are independent checklist roles, not external safety certifiers or five human experts. Only the primary agent changed code, ran the service or accessed cameras.

| Reviewer | Scope |
|---|---|
| `/root/r1_runtime` | Stop/state machine, serial ownership, unique lease/session, cleanup and shutdown |
| `/root/r2_data` | Dataset/action/time semantics, video windows, resume, audit and loader |
| `/root/r3_ui_delivery` | UI payload/receipts, error truthfulness, Windows lifecycle, patch rebuild and test coverage |

## Findings closed

1. Stop no longer aliases timeout or rerecord. Accept, finite Timeout, destructive Discard and Stop have separate decisions; Stop fences command dispatch, skips reset/next episode and saves a non-empty interrupted episode.
2. Hardware ownership uses a unique lease token. Stale controls and delayed cleanup cannot mutate or release a later session. Teleoperation HTTP/WS reads exact-session worker caches and does not reopen the serial bus.
3. Inference and recording cleanup retain their token when process exit is unproven. An error response carries that token back to the UI for exact-session polling/stopping.
4. The UI profile reaches the validated request and constructed runtime configuration. The receipt exposes the returned dataset ID, episode arithmetic, Dataset FPS, resolved camera backend/index/size/capture rate, H.264/PyAV parameters and six target-delta values with units.
5. Frozen profile v2 checks identity, task, local-video flags, FPS, encoder, exact joint keys/units, two distinct camera roles and robot identity before Browse offers resume. Runtime resume still requires full profile equality.
6. Dataset `action` retains the official processed operator-target meaning. Ignored trace evidence separately records requested/to-send/effective-sent/clipped values and pre-command measured state; nominal Dataset time remains distinct from measured host loop/camera arrival timing.
7. Browse/audit is read-only. Every indexed episode requires the matching Parquet action-row count and exactly matching decodable frames from each camera. Requests past physical video EOF return missing instead of the last frame.
8. Both the active and secondary all-camera players clamp playback to their own packed-MP4 episode windows. Partial thumbnail evidence is visible rather than silently shortened.
9. An unload-time teleoperation stop is not reported as clean merely because a keepalive request was sent. The exact token is retained and cached exact-session status must confirm worker exit.
10. Windows PID/listener handling tolerates vanished processes and rejects identity drift. Project stop uses an atomic idle fence; it remains explicitly a software-process fence, not torque-off.

## Rebuild and regression evidence

- Project tests: 54 collected and passed; focused M5 runtime/data subset: 30 passed.
- Pinned LeLab tests: 268 passed offline with PyAV for the Windows video path.
- Frontend: 6 files / 15 tests passed; scoped ESLint passed; production build produced `index-DkcKoWiS.js` and `index-DRCNpsSe.css`.
- The patch applied cleanly to a new detached checkout at exact LeLab commit `6091a458`; 44 source/test files matched the live vendor candidate after LF normalization. Imports resolved from that fresh checkout, then the 54 project tests, 268 vendor tests and 15 frontend tests/build all passed.
- The synthetic HTTP/DataSet v3 test obtains the actual timestamped dataset ID returned by `/start-recording`, finalizes and loads one H.264/Parquet episode locally, resumes that exact ID for two more, then loads a CPU DataLoader batch. Robot, teleoperator, serial, camera and Hub constructors/download paths are intercepted. This is software fixture evidence only.

## Remaining gate

No real recording was started in this review. Real dataset ID is `NOT_RUN`, real episode count is 0, and replay/training/inference are `NOT_RUN`. M5 remains `M5_SOFTWARE_READY / AWAITING_ATTENDED_CAPTURE` until one attended episode is finalized/audited/loaded and the exact returned ID is resumed for two more verified real episodes under one frozen profile.
