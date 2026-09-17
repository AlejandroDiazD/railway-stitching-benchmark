"""Batch evaluation of every wagon of a benchmark dataset.

Walks a tree of stitching results, evaluates each wagon that has a
`frame_offsets.json`, and aggregates the scores into a CSV and a JSON summary.
As in the single-sequence evaluator, no frame images are required.

Expected directory layout (both trees keyed by {train}/{wagon}):
    {results-dir}/{train}/{wagon}/frame_offsets.json    stitching output
    {labels-dir}/{train}/{wagon}/gt_pair_*.json         ground-truth annotations
    {output-dir}/eval_summary.{csv,json}                evaluation output

Usage:
    python evaluate_dataset.py --results-dir /path/to/your/runs \\
                               --labels-dir  /path/to/dataset/annotations \\
                               --output-dir  /path/to/evaluation_output
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import NamedTuple, TypedDict

import offsets as offsets_io
import score as scoring
import tier1_dr
import tier2_da
import tier3_ss

CSV_FIELDS = [
    "train_id", "wagon_id", "system", "n_frames", "n_pairs",
    "n_gt_pairs", "T1", "T2", "T3", "composite", "tiers_used",
]


class WagonTask(NamedTuple):
    """One wagon queued for evaluation."""

    offsets_path: Path
    train_id: str
    wagon_id: str
    labels_dir: Path | None

    @property
    def has_ground_truth(self) -> bool:
        """Whether annotation files are actually present for this wagon."""
        return (self.labels_dir is not None
                and self.labels_dir.exists()
                and any(self.labels_dir.glob("gt_pair_*.json")))


class WagonScores(TypedDict, total=False):
    """Scores of one wagon, or the error that prevented computing them."""

    train_id: str
    wagon_id: str
    system: str
    train: str
    wagon: str
    n_frames: int
    n_pairs: int
    n_gt_pairs: int
    T1: float | None
    T2: float | None
    T3: float | None
    composite: float
    tiers_used: list[str]
    error: str


def evaluate_wagon(offsets_path: Path, labels_dir: Path | None,
                   weights: dict[str, float] | None = None) -> WagonScores:
    """Evaluate a single wagon across the three tiers.

    Args:
        offsets_path: Path to the wagon's `frame_offsets.json`.
        labels_dir: Directory of `gt_pair_*.json` files, or None to skip Tier 2.
        weights: Tier weights to use instead of the defaults, as produced by
            `score.parse_weights`.

    Returns:
        The three tier scores and the composite, with the metadata reported by
        the stitching system.
    """
    data = offsets_io.load(offsets_path)
    offsets_px = data["offsets_px"]

    annotations: list[dict] = []
    if labels_dir is not None and labels_dir.exists():
        annotations = tier2_da.load_annotations(labels_dir)

    t1 = tier1_dr.compute(offsets_px)
    t2 = tier2_da.compute(offsets_px, annotations) if annotations else None
    t3 = tier3_ss.compute(offsets_px)

    composite_score, tiers_used = scoring.composite(
        t1["score"], t2["score"] if t2 else None, t3["score"], weights=weights)

    return WagonScores(
        system=data.get("system", "—"),
        train=data.get("train", "—"),
        wagon=data.get("wagon", "—"),
        n_frames=len(offsets_px),
        n_pairs=max(0, len(offsets_px) - 1),
        n_gt_pairs=len(annotations),
        T1=t1["score"],
        T2=t2["score"] if t2 else None,
        T3=t3["score"],
        composite=float(composite_score),
        tiers_used=tiers_used,
    )


def discover_wagons(
    results_dir: Path,
    labels_dir: Path | None,
    train_filter: list[str] | None,
    wagon_filter: list[str] | None,
) -> list[WagonTask]:
    """Find every wagon under `results_dir` that has a `frame_offsets.json`.

    Args:
        results_dir: Root of the stitching results tree.
        labels_dir: Root of the annotations tree, or None.
        train_filter: Keep only trains whose identifier contains one of these
            substrings. None keeps every train.
        wagon_filter: Keep only wagons with these exact identifiers. None keeps
            every wagon.

    Returns:
        The matching wagons, ordered by path.
    """
    tasks = []
    for offsets_path in sorted(results_dir.rglob("frame_offsets.json")):
        wagon_id = offsets_path.parent.name
        train_id = offsets_path.parent.parent.name

        if train_filter and not any(token in train_id for token in train_filter):
            continue
        if wagon_filter and wagon_id not in wagon_filter:
            continue

        tasks.append(WagonTask(
            offsets_path=offsets_path,
            train_id=train_id,
            wagon_id=wagon_id,
            labels_dir=labels_dir / train_id / wagon_id if labels_dir else None,
        ))
    return tasks


def _mean(values: Iterable[float | None]) -> float | None:
    """Mean of the values that are not None, or None if there are none."""
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def _write_csv(path: Path, rows: list[WagonScores]) -> None:
    """Write one flat row per wagon, ignoring the nested fields."""
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def _parse_args() -> argparse.Namespace:
    """Define and parse the command-line interface."""
    parser = argparse.ArgumentParser(
        description="Batch evaluation of all wagons in a benchmark dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--results-dir", type=Path, required=True,
        help="Root dir with stitching results ({train}/{wagon}/frame_offsets.json)")
    parser.add_argument(
        "--labels-dir", type=Path, default=None,
        help="Root dir with annotations ({train}/{wagon}/gt_pair_*.json)")
    parser.add_argument(
        "--output-dir", type=Path, default=None,
        help="Where to write eval_summary.csv and eval_summary.json "
             "[default: --results-dir]")
    parser.add_argument(
        "--train-filter", nargs="+", default=None,
        help="Only evaluate trains whose name contains any of these substrings")
    parser.add_argument(
        "--wagon-filter", nargs="+", default=None,
        help="Only evaluate wagons with these exact names")
    parser.add_argument(
        "--weights", type=str, default=None, metavar="W1,W2,W3",
        help="Composite exponents for T1,T2,T3; renormalised over the tiers "
             "available, so only their ratios matter "
             f"[default {','.join(str(scoring.TIER_WEIGHTS[t]) for t in ('T1', 'T2', 'T3'))}]")
    return parser.parse_args()


def main() -> None:
    """Evaluate every discovered wagon and write the summaries."""
    args = _parse_args()

    try:
        weights = scoring.parse_weights(args.weights) if args.weights else None
    except ValueError as error:
        sys.exit(f"--weights: {error}")

    output_dir = args.output_dir or args.results_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    tasks = discover_wagons(
        args.results_dir, args.labels_dir, args.train_filter, args.wagon_filter)
    if not tasks:
        sys.exit("No frame_offsets.json found. Check --results-dir.")

    n_annotated = sum(1 for task in tasks if task.has_ground_truth)
    print(f"Wagons with stitching results : {len(tasks)}")
    print(f"Wagons with GT annotations    : {n_annotated}")
    print()

    rows: list[WagonScores] = []
    for index, task in enumerate(tasks, start=1):
        print(f"  [{index:>2}/{len(tasks)}] {task.train_id}/{task.wagon_id}"
              f"  GT={'yes' if task.has_ground_truth else 'NO '}", end="  ", flush=True)
        try:
            row = evaluate_wagon(task.offsets_path, task.labels_dir, weights)
        except (OSError, ValueError, KeyError) as error:
            print(f"ERROR: {error}")
            rows.append(WagonScores(
                train_id=task.train_id, wagon_id=task.wagon_id, error=str(error)))
            continue

        row["train_id"] = task.train_id
        row["wagon_id"] = task.wagon_id
        rows.append(row)

        t2 = f"{row['T2']:.3f}" if row["T2"] is not None else "  — "
        print(f"T1={row['T1']:.3f}  T2={t2}  T3={row['T3']:.3f}  "
              f"composite={row['composite']:.3f}")

    annotated = [row for row in rows if row.get("T2") is not None]
    evaluated = [row for row in rows if "composite" in row]

    summary = {
        "dataset": args.results_dir.name,
        "date": datetime.now().isoformat(),
        "n_wagons_total": len(tasks),
        "n_wagons_annotated": n_annotated,
        "n_wagons_evaluated": len(evaluated),
        "avg_T1_all": _mean(row["T1"] for row in evaluated),
        "avg_T2_annotated": _mean(row["T2"] for row in annotated),
        "avg_T3_all": _mean(row["T3"] for row in evaluated),
        "avg_composite_all": _mean(row["composite"] for row in evaluated),
        "avg_composite_annotated": _mean(row["composite"] for row in annotated),
        "wagons": rows,
    }

    json_path = output_dir / "eval_summary.json"
    csv_path = output_dir / "eval_summary.csv"
    json_path.write_text(json.dumps(summary, indent=2))
    _write_csv(csv_path, rows)

    print()
    print("=" * 60)
    print("DATASET EVALUATION SUMMARY")
    print("=" * 60)
    print(f"  wagons evaluated   : {len(evaluated)}/{len(tasks)}")
    print(f"  wagons with T2     : {len(annotated)}")
    for label, key in (("avg T1 (all)      ", "avg_T1_all"),
                       ("avg T2 (annotated)", "avg_T2_annotated"),
                       ("avg T3 (all)      ", "avg_T3_all")):
        if summary[key] is not None:
            print(f"  {label} : {summary[key]:.3f}")
    if summary["avg_composite_annotated"] is not None:
        print(f"  composite (annot.) : {summary['avg_composite_annotated']:.3f}")
    elif summary["avg_composite_all"] is not None:
        print(f"  composite (all)    : {summary['avg_composite_all']:.3f}")
    print(f"  → {csv_path}")
    print(f"  → {json_path}")


if __name__ == "__main__":
    main()
