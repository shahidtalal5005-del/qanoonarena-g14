# DEVIATIONS.md — Group G14

List every change from the fixed rules in `harness/config.yaml` or the harness code.
If you made no changes, write "None" below and submit this file anyway.
Unreported changes remove your results from the paper and cost the Step 5 marks.

| Date | What we changed | Why | Which results it affects |
| --- | --- | --- | --- |
| 2026-11-25 | Re-executed two evaluation runs (`G14_M0+A1_dev_s2026` and `G14_M2+A1_dev_s13`) using the exact same `A1` QLoRA checkpoint (`adapter_hash: 417bf953ded4`) and fixed `harness/config.yaml` controls (`config_hash: f1c935f7080e`). | A Colab runtime disconnect cleared temporary container storage before the `.csv`, `.pred.jsonl`, and trace `.jsonl` artifacts from the November 24 run could be exported (only the `.json` manifests had been copied to Drive). Re-running produced identical summary scores while restoring complete 1-to-1 trace and prediction logs. | `results/G14_M0+A1_dev_s2026.*`, `results/G14_M2+A1_dev_s13.*`, and their corresponding `traces/*.jsonl` files. |
