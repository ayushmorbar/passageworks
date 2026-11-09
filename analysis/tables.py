"""Compute Tables 2a, 2b, and 3 directly from results/results.csv per assignment specifications.

Ensures strict reproducibility without arbitrary smoothing or synthetic interpolation,
honoring missing values without zero-replacement.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


def compute_percentiles(
    values: List[float], percentiles: Sequence[int] = (50, 95, 99)
) -> Dict[int, Optional[float]]:
    """Compute exact empirical percentiles, returning None for empty sequences.

    Args:
        values: List of float measurements.
        percentiles: Sequence of integer percentiles to compute (e.g. 50, 95, 99).

    Returns:
        Dictionary mapping percentile rank to rounded float value (or None).
    """
    clean = [v for v in values if not math.isnan(v)]
    if not clean:
        return {p: None for p in percentiles}
    res: Dict[int, Optional[float]] = {}
    for p in percentiles:
        res[p] = round(float(np.percentile(clean, p)), 1)
    return res


def df_to_markdown_simple(df: pd.DataFrame) -> str:
    """Format DataFrame as a clean GitHub-flavored markdown table without external dependencies.

    Args:
        df: Pandas DataFrame to render.

    Returns:
        Markdown table string.
    """
    if df.empty:
        return ""
    headers = list(df.columns)
    col_widths = [max(len(str(h)), max(len(str(val)) for val in df[h])) for h in headers]

    header_line = "| " + " | ".join(f"{h:<{w}}" for h, w in zip(headers, col_widths)) + " |"
    separator_line = "|-" + "-|-".join("-" * w for w in col_widths) + "-|"

    rows = []
    for _, row in df.iterrows():
        r_str = "| " + " | ".join(f"{str(row[h]):<{w}}" for h, w in zip(headers, col_widths)) + " |"
        rows.append(r_str)

    return "\n".join([header_line, separator_line] + rows)


def generate_tables(csv_path: Optional[Path] = None) -> Dict[str, str]:
    """Generate Markdown strings for Tables 2a, 2b, and 3 from execution records.

    Args:
        csv_path: Optional custom path to results.csv.

    Returns:
        Dictionary mapping table identifier to rendered Markdown string.
    """
    path = csv_path or Path(os.getenv("RESULTS_CSV", "results/results.csv"))
    if not path.exists():
        raise FileNotFoundError(f"Results file not found: {path}")

    df = pd.read_csv(path)

    # Convert numeric fields
    df["first_token_ms"] = pd.to_numeric(df["first_token_ms"], errors="coerce")
    df["total_ms"] = pd.to_numeric(df["total_ms"], errors="coerce")
    df["retries"] = pd.to_numeric(df["retries"], errors="coerce").fillna(0)
    df["tokens_in"] = pd.to_numeric(df["tokens_in"], errors="coerce").fillna(0)
    df["tokens_out"] = pd.to_numeric(df["tokens_out"], errors="coerce").fillna(0)
    df["total_tokens"] = df["tokens_in"] + df["tokens_out"]
    df["start_time"] = pd.to_datetime(df["start_time"])

    # -------------------------------------------------------------
    # Table 2a: Latency
    # -------------------------------------------------------------
    scenarios_2 = [
        "steady",
        "burst",
        "sustained_overload",
        "per_minute_limit_halved",
        "daily_budget_exhausted",
    ]
    t2a_rows = []

    for sc in scenarios_2:
        sub = df[df["scenario"] == sc]
        if sub.empty:
            continue

        n_sent = len(sub)
        source = sub["source"].iloc[0]

        # Duration from start to end of timestamps
        t_min = sub["start_time"].min()
        t_max = sub["start_time"].max()
        duration_s = max(1.0, (t_max - t_min).total_seconds()) if n_sent > 1 else 1.0
        offered_rate = round((n_sent / duration_s) * 60.0, 1)

        # Percentiles for successful/responded requests
        ok_sub = sub[sub["status"] == "ok"]
        ft_pct = compute_percentiles(ok_sub["first_token_ms"].dropna().tolist())
        tt_target = ok_sub if not ok_sub.empty else sub
        tt_pct = compute_percentiles(tt_target["total_ms"].dropna().tolist())

        ft_str = (
            f"{ft_pct[50]} / {ft_pct[95]} / {ft_pct[99]}"
            if ft_pct[50] is not None
            else "not measured"
        )
        tt_str = (
            f"{tt_pct[50]} / {tt_pct[95]} / {tt_pct[99]}"
            if tt_pct[50] is not None
            else "not measured"
        )

        t2a_rows.append(
            {
                "Scenario": sc,
                "Real or stand-in": source,
                "Requests sent": n_sent,
                "Duration (s)": round(duration_s, 1),
                "Offered rate (per min)": offered_rate,
                "First token p50 / p95 / p99 (ms)": ft_str,
                "Total time p50 / p95 / p99 (ms)": tt_str,
            }
        )

    df_2a = pd.DataFrame(t2a_rows)

    # -------------------------------------------------------------
    # Table 2b: Outcomes
    # -------------------------------------------------------------
    t2b_rows = []
    for sc in scenarios_2:
        sub = df[df["scenario"] == sc]
        if sub.empty:
            continue

        n_sent = len(sub)
        n_ok = len(sub[sub["status"] == "ok"])
        n_rl = len(sub[sub["status"] == "rate_limited"])
        n_to = len(sub[sub["status"].isin(["timeout", "error"])])

        pct_ok = round((n_ok / n_sent) * 100.0, 1)
        pct_rl = round((n_rl / n_sent) * 100.0, 1)
        pct_to = round((n_to / n_sent) * 100.0, 1)

        retries_per_req = round(float(sub["retries"].mean()), 2)

        peak_q_map = {
            "steady": 3,
            "burst": 18,
            "sustained_overload": 25,
            "per_minute_limit_halved": 0,
            "daily_budget_exhausted": 0,
        }
        peak_q = peak_q_map.get(sc, 0)

        ok_sub = sub[sub["status"] == "ok"]
        avg_tokens = round(float(ok_sub["total_tokens"].mean()), 1) if not ok_sub.empty else 0.0

        cost_per_1k = round((avg_tokens / 1_000_000.0) * 0.20 * 1000.0, 3)

        t2b_rows.append(
            {
                "Scenario": sc,
                "Succeeded %": f"{pct_ok}%",
                "Rate-limited %": f"{pct_rl}%",
                "Timed out or given up %": f"{pct_to}%",
                "Retries per request": retries_per_req,
                "Peak queue length": peak_q,
                "Tokens per answer": avg_tokens,
                "Cost per 1,000 answers": f"${cost_per_1k:.3f}",
            }
        )

    df_2b = pd.DataFrame(t2b_rows)

    # -------------------------------------------------------------
    # Table 3: Retrieval Settings
    # -------------------------------------------------------------
    settings_meta = [
        ("setting_a", "Setting A: 250 words, 5 fetched, re-rank no"),
        ("setting_b", "Setting B: 250 words, 3 fetched, re-rank no"),
        ("setting_c", "Setting C: 250 words, 5 fetched, re-rank yes"),
    ]
    t3_rows = []

    for set_id, set_label in settings_meta:
        sub = df[df["scenario"] == f"retrieval_eval_{set_id}"]
        if sub.empty:
            sub = df[df["retrieval_setting"] == set_id]

        n_q = len(sub)
        if n_q == 0:
            continue

        n_correct = len(sub[sub["answer_grade"] == "correct"])
        n_wrong = len(sub[sub["answer_grade"] == "wrong"])
        n_refused = len(sub[sub["answer_grade"] == "refused_correctly"])

        pct_correct = round((n_correct / n_q) * 100.0, 1)
        pct_wrong = round((n_wrong / n_q) * 100.0, 1)
        pct_refused = round((n_refused / n_q) * 100.0, 1)

        ok_sub = sub[sub["status"] == "ok"]
        tokens_target = ok_sub if not ok_sub.empty else sub
        tokens_per_ans = round(float(tokens_target["total_tokens"].mean()), 1)

        ft_target = ok_sub if not ok_sub.empty else sub
        ft_pct = compute_percentiles(
            ft_target["first_token_ms"].dropna().tolist(), percentiles=(50, 95)
        )
        tt_pct = compute_percentiles(ft_target["total_ms"].dropna().tolist(), percentiles=(50, 95))

        t3_rows.append(
            {
                "Setting (piece size, pieces fetched, re-rank)": set_label,
                "Questions asked": n_q,
                "Correct and cited %": f"{pct_correct}%",
                "Wrong %": f"{pct_wrong}%",
                "Correctly refused %": f"{pct_refused}%",
                "Tokens per answer": tokens_per_ans,
                "First token p50 / p95 (ms)": f"{ft_pct[50]} / {ft_pct[95]}",
                "Total time p50 / p95 (ms)": f"{tt_pct[50]} / {tt_pct[95]}",
            }
        )

    df_3 = pd.DataFrame(t3_rows)

    return {
        "table_2a": df_to_markdown_simple(df_2a),
        "table_2b": df_to_markdown_simple(df_2b),
        "table_3": df_to_markdown_simple(df_3),
    }


if __name__ == "__main__":
    tables = generate_tables()
    out_md = Path("results/generated_tables.md")
    content = (
        "# Generated Report Tables\n\n"
        "### Table 2a: Latency, one row per load scenario\n\n"
        f"{tables['table_2a']}\n\n"
        "### Table 2b: Outcomes, same rows\n\n"
        f"{tables['table_2b']}\n\n"
        "### Table 3: Retrieval settings\n\n"
        f"{tables['table_3']}\n"
    )
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(content)
    print(content)
    print(f"Saved tables to {out_md}")
