# Evaluation framework — tier reference

What each tier computes, what it needs, and which options change it. The
definitions, their justification and the validation of the framework are in the
paper; this file is the operational reference. For repository layout, input
format and dataset access, see the [top-level README](../README.md).

All scripts are **pure Python standard library** (Python ≥ 3.9). No frame images
are needed: every tier is computed from `frame_offsets.json`, and T2 additionally
reads the ground-truth annotation files.

Throughout, `dx_i` is the per-pair displacement derived from the offsets:

```
dx_i = offsets_px[i+1] - offsets_px[i]
```

---

## Tier 1 — Degenerate Rate (T1)

Fraction of pairs for which the system reported `dx ≈ 0` while the sequence as a
whole was moving.

```
degenerate:  |dx_i| <= 10 px  AND  median(|dx|) > 50 px

DR = n_degenerate / n_pairs
T1 = 1 - DR
```

If the whole sequence is stationary (`median(|dx|) <= 50 px`), no pair is
flagged and T1 is reported as 1.0 with a note.

**Ground truth:** not required.
**Options:** `--degen-threshold` (default 10 px), `--moving-threshold` (default 50 px).

---

## Tier 2 — Displacement Accuracy (T2)

Per-pair error against the annotated ground truth, scored relative to the
magnitude of the displacement. `dx_gt` is the `gt_dx_median` field of the
annotation file.

```
error = | |dx_est| - |dx_gt| |

score = 1.0                          if error <= 0.05 * |dx_gt|
score = 0.0                          if error >= 0.20 * |dx_gt|
score = linear interpolation in between

T2 = mean(score) over all annotated pairs
```

Annotations are matched to your offsets by `pair_id`. Pairs whose ground truth
is `≈ 0` are reported but excluded from the mean. If no annotations are
supplied, T2 is skipped and the composite is renormalised over T1 and T3.

**Ground truth:** required.
**Options:** `--tolerance` (default 0.05), `--penalty` (default 0.20).

Ground truth per pair is `gt_dx_median`, the **upper median** of the ten
annotated point displacements: with an even number of correspondences it is
the higher of the two central values, not their average. This is the value
used throughout the paper.

---

## Tier 3 — Sequence Stability (T3)

Coefficient of variation of `dx` along the sequence, over moving pairs only
(`|dx| > 50 px`), so stationary and degenerate pairs do not enter the variance.

```
CoV_dx = std(dx_valid) / |mean(dx_valid)|
T3     = max(0, 1 - CoV_dx / 0.50)
```

**Ground truth:** not required.
**Options:** `--max-cov` (default 0.50), `--moving-threshold` (default 50 px).

---

## Composite score

Weighted geometric mean of the available tiers:

```
Composite = T1^0.1 · T2^0.6 · T3^0.3          (weights sum to 1.0)
```

Any tier at 0 drives the composite to 0. When T2 is unavailable the remaining
weights are renormalised over T1 and T3, and the report states which tiers were
used.

---

## Files

| File | Role |
|---|---|
| `evaluate.py` | CLI — evaluates one sequence, prints the report, optionally saves JSON |
| `evaluate_dataset.py` | CLI — batch evaluation over `{train}/{wagon}/` trees, writes CSV + JSON summaries |
| `tier1_dr.py` | T1 Degenerate Rate — `compute(offsets_px, ...)` |
| `tier2_da.py` | T2 Displacement Accuracy — `compute(offsets_px, annotations, ...)` |
| `tier3_ss.py` | T3 Sequence Stability — `compute(offsets_px, ...)` |
| `score.py` | Composite score and report formatting |
| `offsets.py` | Reading `frame_offsets.json` and deriving per-pair displacements |

Every tier module is both importable and runnable standalone:

```python
from tier1_dr import compute
result = compute(offsets_px)      # -> {"score": ..., "n_degenerate": ..., ...}
```
