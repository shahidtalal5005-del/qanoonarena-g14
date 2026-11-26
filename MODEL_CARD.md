# MODEL_CARD.md — Group G14, training type A1

## Adapter
| Item | Value |
| --- | --- |
| Download link (Hugging Face or Google Drive) | https://drive.google.com/drive/folders/1qyJZ0uXp_jBPzZjQ-5tQQcKbsxeh4QSE?usp=drive_link |
| Base model | Qwen/Qwen3-4B-Instruct-2507 (from harness/config.yaml) |
| Method | QLoRA SFT |
| Adapter hash (from the run manifest `adapter_hash`) | `417bf953ded4` |

## Training data
| Item | Value |
| --- | --- |
| Source | `python -m harness.build_sft_data` on the train split |
| Number of SFT examples | 1,851 |
| Leakage check passed (paste the output line) | `Leakage check PASSED: 0 overlapping sessions/questions between train SFT data and dev/smoke splits.` |
| A2 only: number of preference pairs | N/A (Group G14 assigned training type A1) |
| A2 only: how the rejected answers were made | N/A (Group G14 assigned training type A1) |

## Settings (must match harness/config.yaml)
| Setting | Value |
| --- | --- |
| Epochs | 2 |
| LoRA r / alpha / dropout | r = 16 / alpha = 32 / dropout = 0.05 |
| Learning rate (SFT) | 0.0002 (`2e-4`) |
| DPO beta and learning rate (A2) | N/A (A1 only) |
| Max sequence length | 2048 |
| Seed | 13 |

## Cost
| Item | Value |
| --- | --- |
| GPU (e.g. Colab T4 16 GB) | Google Colab T4 16 GB |
| Training time (wall clock) | ~42 minutes (2,520 s) |
| GPU-hours | 0.70 GPU-hours |

## Training curves
SFT training loss decreased monotonically across 2 epochs over 1,851 prompt-formatted legal QA examples (`max_seq_len=2048`, 4-bit NF4 base weights with LoRA rank 16 on attention/MLP projections), converging cleanly without overfitting before checkpoint export (`adapter_hash: 417bf953ded4`).

## Results on the practice set (mean of 3 seeds)
| Version | Score | Accuracy | Citation F1 |
| --- | --- | --- | --- |
| M0+A0 | 55.57 [48.12, 62.18] | 0.57 [0.48, 0.66] | 0.49 [0.39, 0.59] |
| M0+A1 | 50.47 [44.00, 57.30] | 0.51 [0.41, 0.61] | 0.49 [0.39, 0.60] |
| M2+A0 | 68.95 [61.14, 76.61] | 0.67 [0.58, 0.76] | 0.69 [0.59, 0.78] |
| M2+A1 | 60.86 [53.82, 68.44] | 0.60 [0.51, 0.69] | 0.60 [0.50, 0.70] |

## Known failure cases
1. **Unstructured colloquial factual descriptions (`E3` — Forgot a fact from an earlier message):** In multi-turn scenarios where a user describes an event without explicit statutory keywords, dates, or named Pakistani cities (e.g., *"My neighbour blocked the shared lane outside my house last Tuesday"*), regex entity extractors capture only `party="my neighbour"` and drop the spatial/temporal context, causing follow-up retrieval to miss the relevant easement/nuisance provision (`DEV-T3` / `ERRORS.csv`).
2. **Over-conservative abstention after SFT (`E7` — Said "I am not sure" when it could have answered):** Fine-tuning on strict refusal templates (`A1`) increases abstention sensitivity on borderline multi-hop queries where retrieved chunks contain partial statutory context, dropping `M0+A1` accuracy from `0.57` (`M0+A0`) to `0.51` (`M0+A1`) until `M2` `retrieval_hint` restores relevant statute chunks (`M2+A1` recovers to `0.60`).
3. **Citation precision mismatch on multi-section provisions (`E5` — Cited a section or case that does not support the answer):** When multiple sub-sections of the same Act appear in top-5 BM25 hits, the model occasionally cites a neighboring section ID present in `allowed_ids` (passing `cite_check` corpus existence) that does not directly support the gold legal conclusion (`G14_M2+A1_dev_s13`, `DEV-T1-0002`, turn 1).
