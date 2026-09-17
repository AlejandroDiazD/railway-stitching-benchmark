"""Tier 2: Displacement Accuracy against ground truth.

Compares the per-pair displacement estimated by the stitching system against
the manually annotated ground truth, scored relative to the magnitude of the
displacement:

    error = | |dx_estimated| - |dx_gt| |

    score = 1.0   if error <= tolerance * |dx_gt|
    score = 0.0   if error >= penalty_ceiling * |dx_gt|
    score = linear interpolation in between

    T2 = mean(score) over the annotated pairs that match a reported pair

See the paper for the definition of the tier and the choice of the tolerance
band and penalty ceiling.

Standalone usage:
    python tier2_da.py --offsets frame_offsets.json \\
                       --annotations-dir ../examples/annotations

Import usage:
    from tier2_da import compute
    result = compute(offsets_px, annotations)
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import TypedDict

import offsets as offsets_io

DEFAULT_TOLERANCE_FRAC = 0.05
DEFAULT_PENALTY_FRAC = 0.20

_STATIONARY_GT_PX = 1.0


class PairAccuracy(TypedDict):
    """Accuracy of one annotated pair.

    `error_px` and `score` are None for pairs that could not be scored, in
    which case `note` states why.
    """

    pair_id: str
    dx_gt: float | None
    dx_estimated: int | None
    error_px: float | None
    error_frac: float | None
    score: float | None
    note: str


class DisplacementAccuracyResult(TypedDict):
    """Outcome of the Displacement Accuracy tier."""

    score: float | None
    n_evaluated_pairs: int
    mean_error_px: float | None
    per_pair: list[PairAccuracy]
    note: str


def _score_pair(error_px: float, dx_gt_abs: float,
                tolerance_frac: float, penalty_frac: float) -> float:
    """Map an absolute error to [0, 1] relative to the ground-truth magnitude."""
    tolerance_px = tolerance_frac * dx_gt_abs
    ceiling_px = penalty_frac * dx_gt_abs

    if error_px <= tolerance_px:
        return 1.0
    if error_px >= ceiling_px:
        return 0.0
    return 1.0 - (error_px - tolerance_px) / (ceiling_px - tolerance_px)


def compute(
    offsets_px: list[int],
    annotations: list[dict],
    tolerance_frac: float = DEFAULT_TOLERANCE_FRAC,
    penalty_frac: float = DEFAULT_PENALTY_FRAC,
) -> DisplacementAccuracyResult:
    """Score a sequence against its ground-truth annotations.

    Annotations are matched to the reported displacements by `pair_id`, so the
    sequence may contain more pairs than are annotated.

    Args:
        offsets_px: Cumulative canvas x-positions, one per frame, first being 0.
        annotations: Ground-truth records loaded from `gt_pair_XX_YY.json`. Each
            must carry `pair_id` and `gt_dx_median`; records missing either are
            skipped.
        tolerance_frac: Error fraction of |dx_gt| below which a pair scores 1.0.
        penalty_frac: Error fraction of |dx_gt| above which a pair scores 0.0.

    Returns:
        The tier score together with a per-pair breakdown. `score` is None when
        no annotated pair could be evaluated.
    """
    dx_by_pair_id = {
        offsets_io.format_pair_id(index): dx
        for index, dx in enumerate(offsets_io.per_pair_displacements(offsets_px))
    }

    per_pair: list[PairAccuracy] = []

    for annotation in annotations:
        pair_id = annotation.get("pair_id")
        dx_gt_raw = annotation.get("gt_dx_median")
        if pair_id is None or dx_gt_raw is None:
            continue

        if pair_id not in dx_by_pair_id:
            per_pair.append(PairAccuracy(
                pair_id=pair_id, dx_gt=dx_gt_raw, dx_estimated=None,
                error_px=None, error_frac=None, score=None,
                note="pair_id not found in frame_offsets",
            ))
            continue

        dx_estimated = dx_by_pair_id[pair_id]
        dx_gt_abs = abs(float(dx_gt_raw))

        if dx_gt_abs < _STATIONARY_GT_PX:
            per_pair.append(PairAccuracy(
                pair_id=pair_id, dx_gt=dx_gt_raw, dx_estimated=dx_estimated,
                error_px=None, error_frac=None, score=None,
                note="GT dx_median is ~0 — cannot compute accuracy for stationary pair",
            ))
            continue

        error_px = abs(abs(dx_estimated) - dx_gt_abs)
        per_pair.append(PairAccuracy(
            pair_id=pair_id,
            dx_gt=dx_gt_raw,
            dx_estimated=dx_estimated,
            error_px=error_px,
            error_frac=error_px / dx_gt_abs,
            score=_score_pair(error_px, dx_gt_abs, tolerance_frac, penalty_frac),
            note="ok",
        ))

    scores = [pair["score"] for pair in per_pair if pair["score"] is not None]
    errors = [pair["error_px"] for pair in per_pair if pair["error_px"] is not None]

    if not scores:
        return DisplacementAccuracyResult(
            score=None, n_evaluated_pairs=0, mean_error_px=None,
            per_pair=per_pair,
            note="No annotated pairs matched the provided offsets.",
        )

    mean_error_px = statistics.mean(errors)
    return DisplacementAccuracyResult(
        score=statistics.mean(scores),
        n_evaluated_pairs=len(scores),
        mean_error_px=mean_error_px,
        per_pair=per_pair,
        note=f"{len(scores)} GT pairs evaluated, mean error={mean_error_px:.1f} px",
    )


def load_annotations(annotations_dir: Path) -> list[dict]:
    """Load every `gt_pair_*.json` in a directory, ordered by filename.

    Args:
        annotations_dir: Directory holding the ground-truth files of one wagon.

    Returns:
        The parsed annotations; empty if the directory holds none.
    """
    return [
        json.loads(path.read_text())
        for path in sorted(annotations_dir.glob("gt_pair_*.json"))
    ]


def main() -> None:
    """Run the tier standalone over one `frame_offsets.json`."""
    parser = argparse.ArgumentParser(
        description="Tier 2 — Displacement Accuracy: reported dx against ground truth.",
    )
    parser.add_argument(
        "--offsets", type=Path, required=True,
        help="Path to frame_offsets.json")
    parser.add_argument(
        "--annotations-dir", type=Path, required=True,
        help="Directory containing gt_pair_XX_YY.json annotation files")
    parser.add_argument(
        "--tolerance", type=float, default=DEFAULT_TOLERANCE_FRAC,
        help="Error fraction below which a pair scores 1.0 "
             f"[default {DEFAULT_TOLERANCE_FRAC}]")
    parser.add_argument(
        "--penalty", type=float, default=DEFAULT_PENALTY_FRAC,
        help="Error fraction above which a pair scores 0.0 "
             f"[default {DEFAULT_PENALTY_FRAC}]")
    args = parser.parse_args()

    data = offsets_io.load(args.offsets)
    annotations = load_annotations(args.annotations_dir)
    print(f"Loaded {len(annotations)} GT annotations from {args.annotations_dir}")

    result = compute(data["offsets_px"], annotations, args.tolerance, args.penalty)

    print(f"\nSystem  : {data.get('system', '—')}")
    print(f"Sequence: {data.get('wagon', '—')}")
    print(f"GT pairs evaluated : {result['n_evaluated_pairs']}")
    if result["mean_error_px"] is not None:
        print(f"Mean error         : {result['mean_error_px']:.1f} px")

    print("\nPer-pair breakdown:")
    for pair in result["per_pair"]:
        score = f"{pair['score']:.3f}" if pair["score"] is not None else "  N/A "
        error_px = pair["error_px"]
        error = f"{error_px:.1f} px" if error_px is not None else "  —  "
        print(f"  {pair['pair_id']}  dx_est={pair['dx_estimated']}  "
              f"dx_gt={pair['dx_gt']}  error={error}  score={score}  [{pair['note']}]")

    score = f"{result['score']:.4f}" if result["score"] is not None else "N/A"
    print(f"\nT2 score: {score}")


if __name__ == "__main__":
    main()
