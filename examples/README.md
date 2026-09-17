# Example sequence

One complete, runnable example: wagon `wagon_10` of `train_01`, a
daytime container wagon. It exists so that the framework can be inspected and
executed without requesting the full dataset.

```
examples/
├── frame_offsets.json      ← output of the reference system for this wagon
└── annotations/            ← the 9 ground-truth pairs of this wagon
    └── gt_pair_00_01.json … gt_pair_08_09.json
```

No frames are needed: every tier is computed from the offsets, and T2 reads the
annotations.

Run it:

```bash
cd ../evaluation
python evaluate.py --offsets ../examples/frame_offsets.json \
                   --annotations ../examples/annotations
```

Scores: T1 = 1.000, T2 = 1.000 (9 GT pairs, mean error 19.3 px), T3 = 0.990,
composite = 0.997.

## Notes

- **The sequence has 15 frames (14 pairs) and 9 annotated pairs.** T1 and T3 use
  all 14 pairs; T2 uses the 9 with ground truth. This mismatch is normal and the
  evaluator handles it: annotations are matched to your offsets by `pair_id`.
- **`frame_offsets.json` is a real run** of the system described in the paper
  (dense matcher, seven-filter cascade, degenerate-pair recovery), not a
  synthetic best case.
- **The annotation coordinates refer to the full-resolution frames**
  (2048 × 4096 px), which are not in this repository. See
  [Requesting the dataset](../README.md#requesting-the-dataset).
