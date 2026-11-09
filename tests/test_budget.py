"""Unit tests for token and rate budget tracking."""

from passageworks.budget import TokenBudgetTracker


def test_budget_admission_nominal():
    tracker = TokenBudgetTracker(daily_token_limit=1000, tpm_token_limit=500, rpm_limit=10)
    admitted, err = tracker.check_admission(estimated_tokens=100)
    assert admitted is True
    assert err is None


def test_budget_daily_exhaustion():
    tracker = TokenBudgetTracker(daily_token_limit=500, tpm_token_limit=5000, rpm_limit=30)
    tracker.record_usage(prompt_tokens=300, completion_tokens=250)

    admitted, err = tracker.check_admission(estimated_tokens=50)
    assert admitted is False
    assert "Daily token budget exhausted" in err


def test_budget_minute_tpm_exhaustion():
    tracker = TokenBudgetTracker(daily_token_limit=50_000, tpm_token_limit=1000, rpm_limit=30)
    tracker.record_usage(prompt_tokens=400, completion_tokens=500)

    admitted, err = tracker.check_admission(estimated_tokens=200)
    assert admitted is False
    assert "Per-minute token limit near capacity" in err


def test_budget_rpm_limit():
    tracker = TokenBudgetTracker(rpm_limit=3)
    for _ in range(3):
        tracker.record_usage(10, 10)

    admitted, err = tracker.check_admission(estimated_tokens=10)
    assert admitted is False
    assert "Per-minute request limit reached" in err


def test_budget_reset():
    tracker = TokenBudgetTracker(daily_token_limit=100)
    tracker.record_usage(50, 60)
    assert tracker.total_tokens_consumed == 110

    tracker.reset()
    assert tracker.total_tokens_consumed == 0
    assert tracker.total_requests_count == 0
    admitted, _ = tracker.check_admission(10)
    assert admitted is True
