"""
OCR accuracy test: run OCR on sample images and compare against ground truth.

Requires:
  - tests/ground_truth.yaml with expected (date, shift) per image
  - sample_images/ containing the referenced images

Fill in ground_truth.yaml manually from your actual schedules. The test asserts
that OCR accuracy meets OCR_ACCURACY_THRESHOLD (default 80%).

To see per-image and overall accuracy when the test runs, use -s (no capture):
  pytest tests/test_ocr_accuracy.py -v -s
"""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path
from typing import Any

# Minimum fraction of expected shifts that must match (0.0 to 1.0)
OCR_ACCURACY_THRESHOLD = 0.80

# Paths relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_IMAGES_DIR = PROJECT_ROOT / "sample_images"
GROUND_TRUTH_PATH = Path(__file__).resolve().parent / "ground_truth.yaml"


def _load_ground_truth() -> dict[str, list[dict[str, Any]]] | None:
    """Load ground truth YAML. Returns None if file missing or empty."""
    if not GROUND_TRUTH_PATH.exists():
        return None
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data or not isinstance(data, dict):
        return None
    # Filter to non-empty lists only
    return {k: v for k, v in data.items() if isinstance(v, list) and len(v) > 0}


def _expected_pairs(entries: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """Convert ground truth entries to set of (date_str, shift_code)."""
    pairs: set[tuple[str, str]] = set()
    for e in entries:
        date_str = e.get("date")
        shift = (e.get("shift") or "").strip().upper()
        if date_str and shift:
            pairs.add((str(date_str), shift))
    return pairs


def _actual_pairs(schedule: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """Convert schedule from process_schedule_image to set of (date_str, shift_code)."""
    pairs: set[tuple[str, str]] = set()
    for e in schedule:
        d = e.get("date")
        shift = (e.get("shift") or "").strip().upper()
        if d and shift:
            pairs.add((d.isoformat(), shift))
    return pairs


@pytest.fixture(scope="module")
def ground_truth() -> dict[str, list[dict[str, Any]]] | None:
    """Load ground truth once for the module."""
    return _load_ground_truth()


def test_ocr_accuracy_threshold(
    ground_truth: dict[str, list[dict[str, Any]]] | None,
) -> None:
    """
    Run OCR on each image in ground truth and assert accuracy >= OCR_ACCURACY_THRESHOLD.
    Skips if ground truth or sample images are missing.
    """
    if ground_truth is None:
        pytest.skip(
            "ground_truth.yaml missing or empty; add expected shifts to run this test")

    if not SAMPLE_IMAGES_DIR.exists():
        pytest.skip("sample_images/ directory not found")

    from src.services.image_processor import process_schedule_image

    total_expected = 0
    total_correct = 0
    results = []

    for filename, expected_entries in ground_truth.items():
        image_path = SAMPLE_IMAGES_DIR / filename
        if not image_path.exists():
            results.append((filename, None, None, "FILE_NOT_FOUND"))
            continue

        image_bytes = image_path.read_bytes()
        try:
            schedule = process_schedule_image(image_bytes)
        except Exception as e:
            err_msg = str(e).lower()
            if total_expected == 0 and ("telegram" in err_msg or "env" in err_msg or "config" in err_msg):
                pytest.skip(
                    "Config or .env missing (e.g. in CI). Use local .env and config to run OCR accuracy test."
                )
            results.append((filename, 0, len(expected_entries), f"ERROR: {e}"))
            total_expected += len(expected_entries)
            continue

        expected_set = _expected_pairs(expected_entries)
        actual_set = _actual_pairs(schedule)
        correct = len(expected_set & actual_set)
        n_expected = len(expected_set)
        total_expected += n_expected
        total_correct += correct

        accuracy = correct / n_expected if n_expected else 1.0
        results.append((filename, correct, n_expected, accuracy))

    if total_expected == 0:
        pytest.skip("No ground truth entries to check")

    overall_accuracy = total_correct / total_expected
    lines = []
    for filename, correct, n_expected, acc_or_msg in results:
        if isinstance(acc_or_msg, str):
            line = f"  {filename}: {acc_or_msg}"
        else:
            line = f"  {filename}: {correct}/{n_expected} ({acc_or_msg:.1%})"
        lines.append(line)
        print(line)
    summary_line = f"  Overall: {total_correct}/{total_expected} ({overall_accuracy:.1%})"
    lines.append(summary_line)
    print(summary_line)

    assert overall_accuracy >= OCR_ACCURACY_THRESHOLD, (
        f"OCR accuracy {overall_accuracy:.1%} is below threshold {OCR_ACCURACY_THRESHOLD:.0%}\n"
        + "\n".join(lines)
    )
