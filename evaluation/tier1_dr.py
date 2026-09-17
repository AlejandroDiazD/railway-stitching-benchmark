"""Tier 1: Degenerate Rate.

A pair is degenerate when the stitching system reports a near-zero displacement
while the sequence as a whole was moving:

    DR = n_degenerate / n_pairs
    T1 = 1 - DR

If the whole sequence appears stationary, no pair is flagged and T1 is 1.0.

See the paper for the definition of the tier and the choice of thresholds.

Standalone usage:
    python tier1_dr.py --offsets frame_offsets.json

Import usage:
    from tier1_dr import compute
    result = compute([0, -825, -1655])
"""

from __future__ import annotations

import argparse
import statistics
from pathlib import Path
from typing import TypedDict

import offsets as offsets_io

DEFAULT_MOVING_THRESHOLD_PX = 50
DEFAULT_DEGENERATE_THRESHOLD_PX = 10


class DegenerateRateResult(TypedDict):
    """Outcome of the Degenerate Rate tier."""

    score: float
    degenerate_rate: float
    n_degenerate: int
    n_pairs: int
    degenerate_indices: list[int]
    dx_per_pair: list[int]
    median_abs_dx: float
    note: str


def compute(
    offsets_px: list[int],
    moving_threshold_px: int = DEFAULT_MOVING_THRESHOLD_PX,
    degenerate_threshold_px: int = DEFAULT_DEGENERATE_THRESHOLD_PX,
) -> DegenerateRateResult:
    """Score a sequence on the rate of degenerate pairs.

    Args:
        offsets_px: Cumulative canvas x-positions, one per frame, first being 0.
        moving_threshold_px: Minimum median absolute displacement for the
            sequence to count as moving. Below it the train may have been
            stationary and the tier does not penalise.
        degenerate_threshold_px: Maximum absolute displacement at which a pair
            of a moving sequence counts as degenerate.

    Returns:
        The tier score together with the offending pair indices and the
        intermediate quantities behind it.
    """
    dx_per_pair = offsets_io.per_pair_displacements(offsets_px)

    if not dx_per_pair:
        return DegenerateRateResult(
            score=1.0,
            degenerate_rate=0.0,
            n_degenerate=0,
            n_pairs=0,
            degenerate_indices=[],
            dx_per_pair=[],
            median_abs_dx=0.0,
            note="Fewer than 2 frames — nothing to evaluate.",
        )

    abs_dx = [abs(dx) for dx in dx_per_pair]
    median_abs_dx = statistics.median(abs_dx)

    if median_abs_dx <= moving_threshold_px:
        return DegenerateRateResult(
            score=1.0,
            degenerate_rate=0.0,
            n_degenerate=0,
            n_pairs=len(dx_per_pair),
            degenerate_indices=[],
            dx_per_pair=dx_per_pair,
            median_abs_dx=float(median_abs_dx),
            note=(
                f"Sequence appears stationary (median |dx|={median_abs_dx:.1f} px "
                f"≤ moving_threshold={moving_threshold_px} px). T1 not applicable."
            ),
        )

    degenerate_indices = [
        index for index, dx in enumerate(abs_dx) if dx <= degenerate_threshold_px
    ]
    degenerate_rate = len(degenerate_indices) / len(dx_per_pair)

    return DegenerateRateResult(
        score=1.0 - degenerate_rate,
        degenerate_rate=degenerate_rate,
        n_degenerate=len(degenerate_indices),
        n_pairs=len(dx_per_pair),
        degenerate_indices=degenerate_indices,
        dx_per_pair=dx_per_pair,
        median_abs_dx=float(median_abs_dx),
        note=(
            f"{len(degenerate_indices)}/{len(dx_per_pair)} pairs degenerate "
            f"(|dx| ≤ {degenerate_threshold_px} px, "
            f"median |dx|={median_abs_dx:.1f} px)"
        ),
    )


def main() -> None:
    """Run the tier standalone over one `frame_offsets.json`."""
    parser = argparse.ArgumentParser(
        description="Tier 1 — Degenerate Rate: pairs reported as dx≈0 while moving.",
    )
    parser.add_argument(
        "--offsets", type=Path, required=True,
        help="Path to frame_offsets.json produced by the stitching system")
    parser.add_argument(
        "--moving-threshold", type=int, default=DEFAULT_MOVING_THRESHOLD_PX,
        metavar="PX",
        help="Minimum median |dx| (px) for the sequence to count as moving "
             f"[default {DEFAULT_MOVING_THRESHOLD_PX}]")
    parser.add_argument(
        "--degen-threshold", type=int, default=DEFAULT_DEGENERATE_THRESHOLD_PX,
        metavar="PX",
        help="Maximum |dx| (px) at which a pair counts as degenerate "
             f"[default {DEFAULT_DEGENERATE_THRESHOLD_PX}]")
    args = parser.parse_args()

    data = offsets_io.load(args.offsets)
    result = compute(data["offsets_px"], args.moving_threshold, args.degen_threshold)

    print(f"System  : {data.get('system', '—')}")
    print(f"Sequence: {data.get('wagon', '—')}")
    print(f"Pairs   : {result['n_pairs']}")
    print(f"Median |dx| : {result['median_abs_dx']:.1f} px")
    print(f"Degenerate  : {result['n_degenerate']} ({result['degenerate_rate']:.1%})")
    if result["degenerate_indices"]:
        print(f"  Pair indices: {result['degenerate_indices']}")
    print(f"\nT1 score: {result['score']:.4f}")
    print(f"Note    : {result['note']}")


if __name__ == "__main__":
    main()
