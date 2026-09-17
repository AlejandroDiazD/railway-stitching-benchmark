"""Evaluate one stitched sequence against the benchmark.

The stitching system is treated as a black box: its only required output is a
`frame_offsets.json` file (see ../README.md for the format), from which all
three tiers are computed.

    T1  Degenerate Rate        needs only frame_offsets.json
    T2  Displacement Accuracy  needs the ground-truth annotations as well
    T3  Sequence Stability     needs only frame_offsets.json

The composite is the weighted geometric mean of the available tiers. Without
annotations, T2 is skipped and the composite is renormalised over T1 and T3.

Usage:
    python evaluate.py --offsets frame_offsets.json \\
                       --annotations ../examples/annotations \\
                       [--output report.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TypedDict

import offsets as offsets_io
import score as scoring
import tier1_dr
import tier2_da
import tier3_ss


class TierResults(TypedDict):
    """The three tier outcomes, each None when the tier was not computed."""

    T1_degenerate_rate: tier1_dr.DegenerateRateResult | None
    T2_displacement_accuracy: tier2_da.DisplacementAccuracyResult | None
    T3_sequence_stability: tier3_ss.SequenceStabilityResult | None


class EvaluationResult(TypedDict):
    """Full outcome of evaluating one sequence."""

    system: str
    wagon: str
    n_frames: int
    n_pairs: int
    tiers: TierResults
    composite_score: float
    available_tiers: list[str]
    report_text: str


def run(
    offsets_path: Path,
    annotations_dir: Path | None,
    moving_threshold_px: int = tier1_dr.DEFAULT_MOVING_THRESHOLD_PX,
    degenerate_threshold_px: int = tier1_dr.DEFAULT_DEGENERATE_THRESHOLD_PX,
    tolerance_frac: float = tier2_da.DEFAULT_TOLERANCE_FRAC,
    penalty_frac: float = tier2_da.DEFAULT_PENALTY_FRAC,
    max_cov: float = tier3_ss.DEFAULT_MAX_COV,
    weights: dict[str, float] | None = None,
) -> EvaluationResult:
    """Evaluate one sequence across all three tiers.

    Args:
        offsets_path: Path to the `frame_offsets.json` under evaluation.
        annotations_dir: Directory of `gt_pair_*.json` files. When None or
            missing, Tier 2 is skipped.
        moving_threshold_px: Minimum |dx| for a pair to count as moving,
            shared by Tier 1 and Tier 3.
        degenerate_threshold_px: Maximum |dx| at which a pair is degenerate.
        tolerance_frac: Tier 2 error fraction scoring 1.0.
        penalty_frac: Tier 2 error fraction scoring 0.0.
        max_cov: Coefficient of variation at which Tier 3 reaches 0.

    Returns:
        The tier results, the composite, and the rendered report.
    """
    data = offsets_io.load(offsets_path)
    offsets_px = data["offsets_px"]

    annotations: list[dict] = []
    if annotations_dir is not None and annotations_dir.exists():
        annotations = tier2_da.load_annotations(annotations_dir)

    tiers = TierResults(
        T1_degenerate_rate=tier1_dr.compute(
            offsets_px, moving_threshold_px, degenerate_threshold_px),
        T2_displacement_accuracy=tier2_da.compute(
            offsets_px, annotations, tolerance_frac, penalty_frac
        ) if annotations else None,
        T3_sequence_stability=tier3_ss.compute(
            offsets_px, moving_threshold_px, max_cov),
    )

    t1 = tiers["T1_degenerate_rate"]
    t2 = tiers["T2_displacement_accuracy"]
    t3 = tiers["T3_sequence_stability"]

    composite_score, available_tiers = scoring.composite(
        t1["score"] if t1 else None,
        t2["score"] if t2 else None,
        t3["score"] if t3 else None,
        weights=weights,
    )

    system = data.get("system", "—")
    wagon = data.get("wagon", "—")

    return EvaluationResult(
        system=system,
        wagon=wagon,
        n_frames=len(offsets_px),
        n_pairs=max(0, len(offsets_px) - 1),
        tiers=tiers,
        composite_score=float(composite_score),
        available_tiers=available_tiers,
        report_text=scoring.format_report(t1, t2, t3, system_name=system,
                                          wagon=wagon, weights=weights),
    )


def _default_weights_help() -> str:
    """Render the default tier weights as they are typed on the command line."""
    return ",".join(str(scoring.TIER_WEIGHTS[label]) for label in ("T1", "T2", "T3"))


def _parse_args() -> argparse.Namespace:
    """Define and parse the command-line interface."""
    parser = argparse.ArgumentParser(
        description="Railway Wagon Stitching Benchmark — evaluate a stitching system.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full evaluation (with ground truth)
  python evaluate.py \\
      --offsets     my_system/frame_offsets.json \\
      --annotations ../examples/annotations \\
      --output      my_system/eval_report.json

  # Offsets only (T1 + T3)
  python evaluate.py --offsets my_system/frame_offsets.json
        """,
    )
    parser.add_argument(
        "--offsets", type=Path, required=True,
        help="frame_offsets.json produced by the stitching system")
    parser.add_argument(
        "--annotations", type=Path, default=None,
        help="Directory with gt_pair_*.json annotation files (required for T2)")
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Save the full JSON report to this path")
    parser.add_argument(
        "--moving-threshold", type=int,
        default=tier1_dr.DEFAULT_MOVING_THRESHOLD_PX, metavar="PX",
        help="Min |dx| (px) for a pair to count as moving "
             f"[default {tier1_dr.DEFAULT_MOVING_THRESHOLD_PX}]")
    parser.add_argument(
        "--degen-threshold", type=int,
        default=tier1_dr.DEFAULT_DEGENERATE_THRESHOLD_PX, metavar="PX",
        help="Max |dx| (px) at which a pair counts as degenerate "
             f"[default {tier1_dr.DEFAULT_DEGENERATE_THRESHOLD_PX}]")
    parser.add_argument(
        "--tolerance", type=float, default=tier2_da.DEFAULT_TOLERANCE_FRAC,
        help="T2: error fraction below which a pair scores 1.0 "
             f"[default {tier2_da.DEFAULT_TOLERANCE_FRAC}]")
    parser.add_argument(
        "--penalty", type=float, default=tier2_da.DEFAULT_PENALTY_FRAC,
        help="T2: error fraction above which a pair scores 0.0 "
             f"[default {tier2_da.DEFAULT_PENALTY_FRAC}]")
    parser.add_argument(
        "--max-cov", type=float, default=tier3_ss.DEFAULT_MAX_COV,
        help="T3: CoV at which the score reaches 0 "
             f"[default {tier3_ss.DEFAULT_MAX_COV}]")
    parser.add_argument(
        "--weights", type=str, default=None, metavar="W1,W2,W3",
        help="Composite exponents for T1,T2,T3; renormalised over the tiers "
             "available, so only their ratios matter "
             f"[default {_default_weights_help()}]")
    return parser.parse_args()


def main() -> None:
    """Evaluate one sequence and print the report."""
    args = _parse_args()

    try:
        weights = scoring.parse_weights(args.weights) if args.weights else None
    except ValueError as error:
        sys.exit(f"--weights: {error}")

    print("Running Railway Wagon Stitching Benchmark evaluation...")

    result = run(
        offsets_path=args.offsets,
        annotations_dir=args.annotations,
        moving_threshold_px=args.moving_threshold,
        degenerate_threshold_px=args.degen_threshold,
        tolerance_frac=args.tolerance,
        penalty_frac=args.penalty,
        max_cov=args.max_cov,
        weights=weights,
    )

    print()
    print(result["report_text"])

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        report = {key: value for key, value in result.items() if key != "report_text"}
        args.output.write_text(json.dumps(report, indent=2))
        print(f"\nJSON report saved to: {args.output}")


if __name__ == "__main__":
    main()
