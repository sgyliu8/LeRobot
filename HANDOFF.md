# HANDOFF — Bootstrap ready, hardware state unresolved

**Snapshot:** 2026-09-17. **Pack:** 1.0.0. **Software release:** not yet created.
This file is the replaceable live snapshot. Past progress belongs in CHANGELOG.

## Identity and observations

| Field | Observed value / ceiling |
|---|---|
| Intended child root | `C:\Project\Physical_AI\Lerobot` |
| Child local state | Directory exists; empty listing; no own `.git` at inspection |
| Child remote | `https://github.com/sgyliu8/LeRobot.git` |
| Remote state | Public, not a fork, no branches returned, size 0; recheck before first push |
| Parent | `C:\Project\Physical_AI`, branch `codex/m10-learning-resource-integration` |
| Parent HEAD | `14bff36d42d54dd351c59decbcbf4fca3286e257` |
| Parent tracking/exclusion | No tracked Lerobot entries; no matching ignore rule observed |
| MCP host | YangHome; Windows 11 Pro; i5-12450H; 15.8 GB RAM; Intel UHD Graphics |
| Storage observation | C: free 53.4 GB; snapshot, not guaranteed free space at installation |
| User report | Leader + follower + wrist/front cameras connected via USB |
| OS enumeration | COM1 (ACPI communications port), one UGREEN Camera 2K; robot endpoints not identified |
| Actuator power / kit voltage / mounting | UNKNOWN; USB attachment does not resolve them |
| Current candidate stack | LeLab commit 6091a458… + LeRobot v0.6.0 / 30da8e68… |
| Runtime status | NOT_RUN: installation, GUI, camera acquisition, motor connection, calibration, motion, training |

The targeted queries did not open serial ports or cameras. They do not prove absence of hardware on another host or driver failure.
The preparation session did not write to the target/parent repository or operate hardware.
This downloadable archive's static checks are recorded separately in docs/reviews/PACK_VALIDATION.md.

## Active milestone

**M0 — repository and execution identity.** Next ready work after the owner extracts the pack and submits the startup prompt:
prove child/parent boundaries → add narrow parent local exclusion when appropriate → initialize or reconcile the child Git → establish baseline → M1 environment and no-device GUI.
M2 OS identity work can proceed alongside M1. M3 camera preview needs actual camera identification; M4+ needs physical checks and attended session authority.

## Immediate blockers and non-blockers

- Blocking motor work: host/device mismatch, absent role mapping, unverified power/assembly, no attended motion session.
- Not blocking software: GPU absent, motor calibration not yet available, hand-eye calibration not yet performed, unknown camera geometry.
- No current permission to publish private video or launch a paid cloud job.
- No hosted CI has been run for this pack. Existing parent quota information is historical, not assumed current.

## Session-end update fields for Codex

Replace this section with: starting/final root/branch/HEAD/worktree; dependency lock identity; executed commands and outcomes; UI evidence; device mapping level; last stopped/active process; remaining uncertainties; next one ready task.
Record any authorised modification to parent local exclude and the absence of parent tracked changes.
Never update this file to PASS because an installation log or UI page merely looks plausible.
