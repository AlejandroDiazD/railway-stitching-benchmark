"""Composite scoring and report formatting.

The composite is the weighted geometric mean of the available tier scores,
renormalised over whichever tiers could be computed. All functions here are
pure: no I/O, no external dependencies.
"""

from __future__ import annotations

from tier1_dr import DegenerateRateResult
from tier2_da import DisplacementAccuracyResult
from tier3_ss import SequenceStabilityResult

TIER_WEIGHTS = {"T1": 0.1, "T2": 0.6, "T3": 0.3}

_SEPARATOR_WIDTH = 60


def parse_weights(spec: str) -> dict[str, float]:
    """Parse a ``w1,w2,w3`` weight specification into a tier weight mapping.

    The three values are the exponents of T1, T2 and T3 in the geometric mean.
    They need not sum to 1: ``composite`` renormalises over the tiers actually
    available, so only their ratios matter.

    Args:
        spec: Three comma-separated non-negative numbers, e.g. ``"0.1,0.6,0.3"``.

    Returns:
        A mapping in the same shape as `TIER_WEIGHTS`.

    Raises:
        ValueError: If the specification is malformed, negative, or all zero.
    """
    parts = [piece.strip() for piece in spec.split(",")]
    if len(parts) != 3:
        raise ValueError(
            f"expected three comma-separated weights (w1,w2,w3), got {spec!r}")
    try:
        values = [float(piece) for piece in parts]
    except ValueError as exc:
        raise ValueError(f"weights must be numbers, got {spec!r}") from exc
    if any(value < 0 for value in values):
        raise ValueError(f"weights must be non-negative, got {spec!r}")
    if sum(values) == 0:
        raise ValueError("at least one weight must be greater than zero")
    return dict(zip(("T1", "T2", "T3"), values))


def composite(
    t1: float | None,
    t2: float | None = None,
    t3: float | None = None,
    weights: dict[str, float] | None = None,
) -> tuple[float, list[str]]:
    """Combine the available tier scores into a single figure.

    Weights are renormalised over the tiers actually supplied, which preserves
    the property that a score of 0 on any one of them collapses the composite
    to 0. See the paper for the choice of weights.

    Args:
        t1: Degenerate Rate score, or None if not computed.
        t2: Displacement Accuracy score, or None if no ground truth was given.
        t3: Sequence Stability score, or None if not computed.
        weights: Tier weights to use instead of `TIER_WEIGHTS`, as produced by
            `parse_weights`. Supplied by the CLI so that the weighting can be
            swept without editing the source.

    Returns:
        The composite score in [0, 1], and the labels of the tiers that went
        into it. Returns `(0.0, [])` when no tier is available.
    """
    tier_weights = TIER_WEIGHTS if weights is None else weights

    available = [(label, score)
                 for label, score in (("T1", t1), ("T2", t2), ("T3", t3))
                 if score is not None]
    if not available:
        return 0.0, []

    total_weight = sum(tier_weights[label] for label, _ in available)
    if total_weight == 0:
        return 0.0, []

    product = 1.0
    for label, score in available:
        weight = tier_weights[label] / total_weight
        product *= max(0.0, float(score)) ** weight

    return product, [label for label, _ in available]


def _format_score(score: float | None) -> str:
    """Render a tier score, or mark it as not evaluated."""
    return f"{score:.4f}" if score is not None else "N/A (not evaluated)"


def format_report(
    t1_result: DegenerateRateResult | None,
    t2_result: DisplacementAccuracyResult | None,
    t3_result: SequenceStabilityResult | None,
    system_name: str = "—",
    wagon: str = "—",
    weights: dict[str, float] | None = None,
) -> str:
    """Render the tier scores and the composite as a human-readable report.

    Args:
        t1_result: Result of the Degenerate Rate tier, or None if skipped.
        t2_result: Result of the Displacement Accuracy tier, or None if skipped.
        t3_result: Result of the Sequence Stability tier, or None if skipped.
        system_name: Name of the system under evaluation, for the header.
        wagon: Sequence identifier, for the header.
        weights: Tier weights to use instead of `TIER_WEIGHTS`, so that the
            printed composite matches the one in the JSON report.

    Returns:
        The report as a single multi-line string, without a trailing newline.
    """
    t1 = t1_result["score"] if t1_result else None
    t2 = t2_result["score"] if t2_result else None
    t3 = t3_result["score"] if t3_result else None

    composite_score, used_tiers = composite(t1, t2, t3, weights=weights)

    double_rule = "=" * _SEPARATOR_WIDTH
    single_rule = "-" * _SEPARATOR_WIDTH

    lines = [
        double_rule,
        "RAILWAY WAGON STITCHING BENCHMARK — EVALUATION REPORT",
        double_rule,
        f"System  : {system_name}",
        f"Sequence: {wagon}",
        "",
        "TIER SCORES",
        single_rule,
        f"T1  Degenerate Rate         : {_format_score(t1)}",
    ]

    if t1_result:
        lines.append(f"    DR={t1_result['degenerate_rate']:.3f}  "
                     f"({t1_result['n_degenerate']}/{t1_result['n_pairs']} "
                     "pairs degenerate)")

    lines.append(f"T2  Displacement Accuracy    : {_format_score(t2)}")

    if t2_result and t2_result["mean_error_px"] is not None:
        lines.append(f"    {t2_result['n_evaluated_pairs']} GT pairs  "
                     f"mean_error={t2_result['mean_error_px']:.1f} px")

    lines.append(f"T3  Sequence Stability       : {_format_score(t3)}")

    if t3_result and t3_result["cov_dx"] is not None:
        lines.append(f"    CoV_dx={t3_result['cov_dx']:.3f}  "
                     f"dx_std={t3_result['dx_std_px']:.1f} px")

    lines += [
        "",
        single_rule,
        f"Composite score [{', '.join(used_tiers)}]  : {composite_score:.4f}",
        double_rule,
    ]

    return "\n".join(lines)
