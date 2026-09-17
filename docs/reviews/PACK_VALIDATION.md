# Pack validation — documentation delivery only

**Date:** 2026-09-17. **Scope:** delivered engineering context pack, not an installed robot application.
**Environment:** artifact-generation container, CPython 3.13.5; not the user's Windows robot host.
**Result:** PACK_STATIC_PASS. Hardware and LeLab runtime remain NOT_RUN.

## 1. Checks actually executed

| Check | Actual result | Evidence boundary |
|---|---|---|
| `python tools/validate_pack.py` | PASS | Required files, UTF-8 text, local file links, source IDs, JSON syntax and selected example semantics |
| `python -m unittest discover -s tests -p "test_validate_pack.py" -v` | 14/14 PASS | Temporary-copy tests; no network or hardware |
| `python tools/validate_pack.py --strict` | PASS on final delivery | Initial manifest file lengths; not a cryptographic guarantee |
| JSON Schema metaschema checks | 2/2 PASS | Draft 2020-12, using jsonschema 4.26.0 in the generation container |
| Example vs own schema | 2/2 PASS | lab.example and run.example are project schemas, not upstream API acceptance |
| Motion-enabled negative schema check | PASS: rejected with 8 prerequisite violations | Schema rejects enabling movement without the template's required facts; no real permission enforcement proven |
| AGENTS context size | 9,451 bytes | Below 32 KiB by itself; actual global/ancestor context must still be inspected by Codex |
| Reviewed source records | 25 | Bounded source/metadata/code-excerpt audit, not exhaustive Web or repository review |
| Review execution | Five roles × three rounds | One assistant using five perspectives; not independent external review |

The unit tests cover missing authorities, wrong repository, motion enabled in a safe example, external upload defaults, floating upstream revision, duplicate camera identity, broken local link, missing source identity, malformed JSON, invented runtime result, delivery size drift, illustrative code links and acceptance of future implementation files.

## 2. Re-run locally

```powershell
python tools/validate_pack.py
python -m unittest discover -s tests -p "test_validate_pack.py" -v
```

Use `--strict` only for an untouched extracted delivery. Once Codex adds implementation or changes documents, normal mode is the appropriate check; the initial manifest remains a delivery snapshot, not current runtime truth.

The standard-library validator checks selected semantic constraints and JSON syntax, not every JSON Schema rule. Full schema tests above used the generation container's already available jsonschema installation. No user dependency was installed for them.

Markdown validation checks local file targets, not heading anchors, rendered Mermaid, external HTTP availability or UI accessibility. The safe examples are illustrative; an operator's local runtime config belongs outside Git and must undergo the later runtime checks.

## 3. Not performed

No target Git initialization/push, parent exclusion edit, Windows environment install, LeLab execution, Browser/Computer Use session, camera access, motor access, calibration, teleoperation, robot recording, replay, training or inference was performed in preparing this pack.
The earlier MCP inspection was OS/file/Git metadata read-only. It is not a camera or robot connection test.
No hosted CI or external reviewer run was performed.

## 4. Integrity and release

PACK_MANIFEST.json lists all delivered files except itself and records byte sizes. The ZIP has a separate SHA-256 file generated once at release; this detects transfer differences, not correctness or safety.
No font, upstream code archive, private camera image, serial identifier, credential, calibration artifact, model weight or dataset is included.

## 5. Next validation authority

Codex must implement and execute the relevant IDs in [TEST_PLAN](../TEST_PLAN.md) as it progresses through [ROADMAP](../ROADMAP.md).
Do not change M1–M8 to PASS based on the static results above.
