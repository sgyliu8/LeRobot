# Experiment Record Template

复制到本地 `.local/experiments/<run_id>/` 填写；需要公开时另导出脱敏摘要。
所有未测字段写 UNKNOWN / NOT_RUN，不补零。

| Field | Value |
|---|---|
| run_id / task / question | UNKNOWN |
| observed_at / timezone | UNKNOWN |
| project commit / upstream commits / dependency lock | UNKNOWN |
| device role mapping / calibration identity | UNKNOWN |
| wrist/front keys / backend / actual shape / fps | UNKNOWN |
| joint order / unit / gripper semantics | UNKNOWN |
| action requested/sent/measured provenance | UNKNOWN |
| task success / initial-state domain / stop rule | UNKNOWN |
| dataset identity / episode counts / split | UNKNOWN |
| missing/invalid data and interruption | UNKNOWN |
| compute / resource observations | UNKNOWN |
| model/checkpoint/processor identity (where relevant) | NOT_RUN |
| bench permission and mode (where relevant) | NOT_RUN |
| commands / tests / evidence artifact IDs | NOT_RUN |
| findings / failures / uncertainty / next change | UNKNOWN |

Local-only: raw paths、serials、calibration、videos、screenshots。
A result is bounded to this task/scene/version; no automatic generalisation or safety claim.
