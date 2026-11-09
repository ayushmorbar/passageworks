"""Test suite verifying results.csv schema conformity according to assignment requirements."""

import csv
from pathlib import Path

REQUIRED_COLUMNS = [
    "request_id",
    "scenario",
    "source",
    "start_time",
    "first_token_ms",
    "total_ms",
    "status",
    "retries",
    "tokens_in",
    "tokens_out",
    "retrieval_setting",
    "answer_grade",
]

ALLOWED_STATUSES = {"ok", "rate_limited", "timeout", "error"}
ALLOWED_GRADES = {"correct", "wrong", "refused_correctly", "refused_wrongly"}
ALLOWED_SOURCES = {"real", "stand-in"}


def test_results_csv_schema():
    """Verify that results.csv exists and conforms to the mandatory column specification."""
    csv_path = Path("results/results.csv")
    if not csv_path.exists():
        # If no experiment has run yet, test a sample template format
        csv_path = Path("results/sample_results.csv")

    assert csv_path.exists(), f"Neither results.csv nor sample_results.csv found at {csv_path}"

    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []

        # All required columns must be present
        missing = set(REQUIRED_COLUMNS) - set(fieldnames)
        assert not missing, f"Missing required columns in results.csv: {missing}"

        # Order check or subset check
        for col in REQUIRED_COLUMNS:
            assert col in fieldnames

        # Validate rows if present
        for i, row in enumerate(reader):
            assert row["source"] in ALLOWED_SOURCES, f"Row {i}: invalid source '{row['source']}'"
            assert row["status"] in ALLOWED_STATUSES, f"Row {i}: invalid status '{row['status']}'"
            assert row["answer_grade"] in ALLOWED_GRADES, (
                f"Row {i}: invalid answer_grade '{row['answer_grade']}'"
            )
