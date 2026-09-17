"""Reading and interpreting the `frame_offsets.json` file under evaluation.

Every tier derives its input from the same two operations: loading the file
emitted by the stitching system, and turning its cumulative canvas positions
into per-pair displacements.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict


class OffsetsFile(TypedDict, total=False):
    """Contents of a `frame_offsets.json` file.

    Only `offsets_px` is required; the remaining fields are reporting metadata.
    """

    offsets_px: list[int]
    frames: list[str]
    system: str
    wagon: str
    train: str


def load(path: Path) -> OffsetsFile:
    """Load a `frame_offsets.json` file.

    Args:
        path: Path to the file emitted by the stitching system.

    Returns:
        The parsed file contents.

    Raises:
        KeyError: If the file has no `offsets_px` field.
    """
    with open(path) as handle:
        data: OffsetsFile = json.load(handle)
    if "offsets_px" not in data:
        raise KeyError(f"{path} has no 'offsets_px' field")
    return data


def per_pair_displacements(offsets_px: list[int]) -> list[int]:
    """Convert cumulative canvas positions into per-pair displacements.

    Args:
        offsets_px: Cumulative horizontal canvas position of each frame, one
            per frame, the first being 0.

    Returns:
        The displacement of each consecutive pair, `len(offsets_px) - 1` items.
        Empty if fewer than two frames were supplied.
    """
    return [second - first for first, second in zip(offsets_px, offsets_px[1:])]


def format_pair_id(index: int) -> str:
    """Return the identifier of the pair starting at `index`, e.g. `"00_01"`."""
    return f"{index:02d}_{index + 1:02d}"
