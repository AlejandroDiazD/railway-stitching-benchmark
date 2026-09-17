"""Tier 3: Sequence Stability.

Coefficient of variation of the inter-frame displacement along a sequence, over
moving pairs only:

    CoV_dx = std(dx_valid) / |mean(dx_valid)|
    T3     = max(0, 1 - CoV_dx / max_cov)

    CoV_dx = 0.00  ->  T3 = 1.00
    CoV_dx = 0.10  ->  T3 = 0.80
    CoV_dx = 0.20  ->  T3 = 0.60
    CoV_dx = 0.50  ->  T3 = 0.00

See the paper for the definition of the tier and the choice of max_cov.

Standalone usage:
    python tier3_ss.py --offsets frame_offsets.json

Import usage:
    from tier3_ss import compute
    result = compute([0, -825, -1655])
"""

from __future__ import annotations

import argparse
import statistics
from pathlib import Path
from typing import TypedDict

import offsets as offsets_io

DEFAULT_MOVING_THRESHOLD_PX = 50
DEFAULT_MAX_COV = 0.50

_MIN_MOVING_PAIRS = 2
_NEGLIGIBLE_MEAN_PX = 1e-6


class SequenceStabilityResult(TypedDict):
    """Outcome of the Sequence Stability tier.

    `cov_dx` is None when the mean displacement is too close to zero for the
    coefficient of variation to be defined.
    """

    score: float
    cov_dx: float | None
    dx_mean_px: float
    dx_std_px: float
    dx_range_px: float
    n_valid: int
    n_excluded: int
    dx_per_pair: list[int]
    note: str


def _not_assessable(dx_per_pair: list[int], *, n_valid: int,
                    note: str) -> SequenceStabilityResult:
    """Build the neutral result used when stability cannot be measured."""
    return SequenceStabilityResult(
        score=1.0,
        cov_dx=0.0,
        dx_mean_px=0.0,
        dx_std_px=0.0,
        dx_range_px=0.0,
        n_valid=n_valid,
        n_excluded=len(dx_per_pair) - n_valid,
        dx_per_pair=dx_per_pair,
        note=note,
    )


def compute(
    offsets_px: list[int],
    moving_threshold_px: int = DEFAULT_MOVING_THRESHOLD_PX,
    max_cov: float = DEFAULT_MAX_COV,
) -> SequenceStabilityResult:
    """Score a sequence on the consistency of its displacement signal.

    Args:
        offsets_px: Cumulative canvas x-positions, one per frame, first being 0.
        moving_threshold_px: Minimum absolute displacement for a pair to enter
            the computation, so that stationary and degenerate pairs do not
            contaminate the variance. Should match the value used for Tier 1.
        max_cov: Coefficient of variation at which the score reaches 0.

    Returns:
        The tier score together with the displacement statistics behind it. A
        sequence with fewer than two moving pairs is not penalised.
    """
    dx_per_pair = offsets_io.per_pair_displacements(offsets_px)

    if len(dx_per_pair) < _MIN_MOVING_PAIRS:
        return _not_assessable(
            dx_per_pair, n_valid=0,
            note="Fewer than 3 frames — stability cannot be assessed.")

    moving_dx = [dx for dx in dx_per_pair if abs(dx) > moving_threshold_px]

    if len(moving_dx) < _MIN_MOVING_PAIRS:
        return _not_assessable(
            dx_per_pair, n_valid=len(moving_dx),
            note="Fewer than 2 moving pairs — stability not assessable "
                 "(train stationary?).")

    mean_dx = statistics.mean(moving_dx)
    std_dx = statistics.stdev(moving_dx)
    range_dx = max(moving_dx) - min(moving_dx)

    if abs(mean_dx) < _NEGLIGIBLE_MEAN_PX:
        cov_dx = None
        score = 0.0
        note = "mean_dx ≈ 0 — undefined CoV (all displacements near zero)."
    else:
        cov_dx = std_dx / abs(mean_dx)
        score = max(0.0, 1.0 - cov_dx / max_cov)
        note = (f"CoV_dx={cov_dx:.3f}, mean={mean_dx:.1f}px, std={std_dx:.1f}px, "
                f"range={range_dx:.0f}px  ({len(moving_dx)} moving pairs)")

    return SequenceStabilityResult(
        score=score,
        cov_dx=cov_dx,
        dx_mean_px=float(mean_dx),
        dx_std_px=float(std_dx),
        dx_range_px=float(range_dx),
        n_valid=len(moving_dx),
        n_excluded=len(dx_per_pair) - len(moving_dx),
        dx_per_pair=dx_per_pair,
        note=note,
    )


def main() -> None:
    """Run the tier standalone over one `frame_offsets.json`."""
    parser = argparse.ArgumentParser(
        description="Tier 3 — Sequence Stability: CoV of the inter-frame displacement.",
    )
    parser.add_argument(
        "--offsets", type=Path, required=True,
        help="Path to frame_offsets.json")
    parser.add_argument(
        "--moving-threshold", type=int, default=DEFAULT_MOVING_THRESHOLD_PX,
        metavar="PX",
        help="Minimum |dx| (px) for a pair to count as moving "
             f"[default {DEFAULT_MOVING_THRESHOLD_PX}]")
    parser.add_argument(
        "--max-cov", type=float, default=DEFAULT_MAX_COV,
        help=f"CoV at which the score reaches 0 [default {DEFAULT_MAX_COV}]")
    args = parser.parse_args()

    data = offsets_io.load(args.offsets)
    offsets_px = data["offsets_px"]
    result = compute(offsets_px, args.moving_threshold, args.max_cov)

    print(f"System  : {data.get('system', '—')}")
    print(f"Sequence: {data.get('wagon', '—')}")
    print(f"Pairs   : {len(offsets_px) - 1}  "
          f"(moving: {result['n_valid']}, excluded: {result['n_excluded']})")
    print(f"dx per pair: {result['dx_per_pair']}")
    print(f"\nMean dx : {result['dx_mean_px']:.1f} px")
    print(f"Std  dx : {result['dx_std_px']:.1f} px")
    print(f"Range   : {result['dx_range_px']:.0f} px")
    cov_dx = f"{result['cov_dx']:.4f}" if result["cov_dx"] is not None else "undefined"
    print(f"CoV_dx  : {cov_dx}")
    print(f"\nT3 score: {result['score']:.4f}")
    print(f"Note    : {result['note']}")


if __name__ == "__main__":
    main()
