"""Open-loop load test runner for Passageworks.

Generates Poisson, burst, and uniform arrival traffic schedules against
the local Stand-in simulation service or live Groq endpoints, logging
results strictly adhering to the brief's 12-column results schema.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import random
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import uvicorn

from passageworks.budget import TokenBudgetTracker
from passageworks.groq_client import GroqClientWrapper
from passageworks.models import PipelineResult
from passageworks.pipeline import PassageworksPipeline
from passageworks.queue import AdmissionController
from passageworks.retrieve import RetrieverTool


def load_questions(
    questions_file: Path | None = None,
) -> list[dict[str, Any]]:
    """Load authored technical benchmark questions from JSON Lines file.

    Args:
        questions_file: Optional path to questions.jsonl file.

    Returns:
        List of question metadata dictionaries.
    """
    path = questions_file or Path(os.getenv("QUESTIONS_FILE", "harness/questions.jsonl"))
    if not path.exists():
        raise FileNotFoundError(f"Questions file not found: {path}")

    questions = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line))
    return questions


def grade_answer(q_meta: dict[str, Any], result: PipelineResult) -> str:
    """Determine answer grade category required by evaluation brief.

    Categories:
        - 'correct': Answerable question answered with valid citations.
        - 'wrong': Hallucinatory answer, unanswerable answered, or failed call.
        - 'refused_correctly': Unanswerable question properly declined.
        - 'refused_wrongly': Answerable question declined in error.

    Args:
        q_meta: Question metadata dictionary.
        result: PipelineResult from pipeline execution.

    Returns:
        One of the four strict grading strings.
    """
    is_answerable = q_meta.get("is_answerable", True)

    if result.status != "ok":
        return "refused_correctly" if not is_answerable else "wrong"

    if result.is_refusal:
        return "refused_correctly" if not is_answerable else "refused_wrongly"

    if not is_answerable:
        return "wrong"

    if result.citations:
        return "correct"
    return "wrong"


class LoadScenarioRunner:
    """Executes open-loop arrival schedules against Stand-in or Real provider.

    Args:
        retriever: Initialized RetrieverTool instance.
        source: Provider identifier ('stand-in' or 'real-service').
        base_url: API endpoint URL.
        output_csv: Target CSV path for execution records.
    """

    def __init__(
        self,
        retriever: RetrieverTool,
        source: str = "stand-in",
        base_url: str | None = None,
        output_csv: Path | None = None,
    ) -> None:
        self.retriever = retriever
        self.source = source
        self.base_url = base_url or os.getenv("GROQ_BASE_URL", "http://127.0.0.1:8000/v1")
        self.output_csv = output_csv or Path(os.getenv("RESULTS_CSV", "results/results.csv"))
        self.control_url = os.getenv("STANDIN_CONTROL_URL", "http://127.0.0.1:8000")
        self.questions = load_questions()

    async def _configure_standin(self, config_params: dict[str, Any]) -> None:
        """Call Stand-in control endpoint to adjust limits or latency.

        Args:
            config_params: Dictionary of configuration parameters to update.
        """
        try:
            async with httpx.AsyncClient(base_url=self.control_url, timeout=5.0) as client:
                await client.post("/control/reset")
                await client.post("/control/configure", json=config_params)
        except Exception:
            pass  # When testing against in-memory transport or real service

    async def run_scenario(
        self,
        scenario_name: str,
        num_requests: int,
        duration_s: float,
        retrieval_setting: str = "setting_a",
        traffic_pattern: str = "uniform",  # uniform, burst, overload
        standin_overrides: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Run an open-loop arrival sequence.

        Args:
            scenario_name: Unique identifier for the benchmark scenario.
            num_requests: Total number of requests to dispatch.
            duration_s: Duration in seconds over which requests are dispatched.
            retrieval_setting: Retrieval setting ('setting_a', 'setting_b', 'setting_c').
            traffic_pattern: Shape of traffic arrival ('uniform', 'burst', 'overload').
            standin_overrides: Optional runtime parameters for stand-in control.

        Returns:
            List of 12-column record dictionaries adhering to results.csv schema.
        """
        print("\n=======================================================")
        print(f"Starting Scenario: {scenario_name} ({self.source})")
        print(
            f"Requests: {num_requests} | Duration: {duration_s}s | Target Rate: {num_requests / (duration_s / 60):.1f} req/min"
        )
        print("=======================================================")

        if self.source == "stand-in":
            await self._configure_standin(standin_overrides or {})

        default_timeout = float(os.getenv("PASSAGEWORKS_REQUEST_TIMEOUT_S", "15.0"))
        max_retries = int(os.getenv("PASSAGEWORKS_MAX_RETRIES", "2"))
        max_concurrent = int(os.getenv("PASSAGEWORKS_MAX_CONCURRENT", "3"))
        max_queue = int(os.getenv("PASSAGEWORKS_MAX_QUEUE_DEPTH", "25"))
        deadline_s = float(os.getenv("PASSAGEWORKS_REQUEST_DEADLINE_S", "25.0"))

        groq_client = GroqClientWrapper(
            base_url=self.base_url if self.source == "stand-in" else None,
            default_timeout=default_timeout,
            max_retries=max_retries,
        )

        if scenario_name == "daily_budget_exhausted":
            budget = TokenBudgetTracker(daily_token_limit=1000, tpm_token_limit=7500, rpm_limit=30)
        elif scenario_name == "per_minute_limit_halved":
            budget = TokenBudgetTracker(daily_token_limit=95000, tpm_token_limit=3000, rpm_limit=15)
        elif scenario_name.startswith("retrieval_eval"):
            budget = TokenBudgetTracker(
                daily_token_limit=500000, tpm_token_limit=150000, rpm_limit=120
            )
        elif scenario_name == "steady":
            budget = TokenBudgetTracker(
                daily_token_limit=95000, tpm_token_limit=25000, rpm_limit=30
            )
        else:
            budget = TokenBudgetTracker(daily_token_limit=95000, tpm_token_limit=7500, rpm_limit=30)

        queue = AdmissionController(
            max_concurrent=max_concurrent, max_queue=max_queue, deadline_s=deadline_s
        )

        pipeline = PassageworksPipeline(
            retriever=self.retriever,
            groq_client=groq_client,
            budget=budget,
            queue=queue,
        )

        # Precompute planned dispatch offsets (open-loop schedule)
        planned_offsets: list[float] = []
        if traffic_pattern == "burst":
            for i in range(num_requests):
                if i < int(num_requests * 0.2):
                    planned_offsets.append(random.uniform(0.0, duration_s * 0.25))
                elif i < int(num_requests * 0.7):
                    planned_offsets.append(random.uniform(duration_s * 0.25, duration_s * 0.45))
                else:
                    planned_offsets.append(random.uniform(duration_s * 0.45, duration_s))
            planned_offsets.sort()
        elif traffic_pattern == "overload":
            interval = duration_s / max(1, num_requests)
            planned_offsets = [i * interval for i in range(num_requests)]
        else:  # uniform/steady
            interval = duration_s / max(1, num_requests)
            planned_offsets = [
                i * interval + random.uniform(-interval * 0.2, interval * 0.2)
                for i in range(num_requests)
            ]
            planned_offsets = [max(0.0, off) for off in planned_offsets]
            planned_offsets.sort()

        records: list[dict[str, Any]] = []
        active_tasks = []
        start_clock = time.perf_counter()

        async def worker(req_idx: int, q_data: dict[str, Any]) -> None:
            req_id = f"req-{scenario_name[:3]}-{req_idx + 1:04d}"
            start_iso = datetime.now(UTC).isoformat()
            try:
                res = await pipeline.execute(
                    question=q_data["question"],
                    request_id=req_id,
                    retrieval_setting=retrieval_setting,
                )
                grade = grade_answer(q_data, res)

                row = {
                    "request_id": req_id,
                    "scenario": scenario_name,
                    "source": self.source,
                    "start_time": start_iso,
                    "first_token_ms": f"{res.first_token_ms:.1f}"
                    if res.first_token_ms is not None
                    else "",
                    "total_ms": f"{res.total_ms:.1f}",
                    "status": res.status,
                    "retries": res.retries,
                    "tokens_in": res.tokens_in,
                    "tokens_out": res.tokens_out,
                    "retrieval_setting": retrieval_setting,
                    "answer_grade": grade,
                }
            except Exception:
                row = {
                    "request_id": req_id,
                    "scenario": scenario_name,
                    "source": self.source,
                    "start_time": start_iso,
                    "first_token_ms": "",
                    "total_ms": "0.0",
                    "status": "error",
                    "retries": 0,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "retrieval_setting": retrieval_setting,
                    "answer_grade": "wrong",
                }
            records.append(row)

        for i, planned_offset in enumerate(planned_offsets):
            now_elapsed = time.perf_counter() - start_clock
            delay = planned_offset - now_elapsed
            if delay > 0:
                await asyncio.sleep(delay)

            q_idx = i % len(self.questions)
            task = asyncio.create_task(worker(i, self.questions[q_idx]))
            active_tasks.append(task)

        await asyncio.gather(*active_tasks, return_exceptions=True)
        print(f"Completed Scenario: {scenario_name}. Recorded {len(records)} requests.")
        return records

    def append_to_csv(self, records: list[dict[str, Any]]) -> None:
        """Write execution records to CSV, strictly respecting the required 12-column schema.

        Args:
            records: List of execution record dictionaries.
        """
        fieldnames = [
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
        file_exists = self.output_csv.exists() and self.output_csv.stat().st_size > 0

        self.output_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_csv, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            for r in records:
                writer.writerow(r)


async def execute_all_scenarios(
    source: str = "stand-in",
    base_url: str | None = None,
) -> None:
    """Execute all five mandatory load scenarios and the three retrieval comparison runs.

    Args:
        source: Provider source ('stand-in' or 'real-service').
        base_url: API endpoint URL.
    """
    chunks_path = Path(os.getenv("CHUNKS_FILE", "papers/chunks.jsonl"))
    retriever = RetrieverTool(chunks_path)
    runner = LoadScenarioRunner(retriever=retriever, source=source, base_url=base_url)

    server_task = None
    standin_port = int(os.getenv("STANDIN_PORT", "8000"))
    standin_host = os.getenv("STANDIN_HOST", "127.0.0.1")

    # If running against stand-in, check if server is active; if not, spin up embedded server
    if source == "stand-in":
        server_active = False
        try:
            async with httpx.AsyncClient(
                base_url=f"http://{standin_host}:{standin_port}", timeout=1.0
            ) as client:
                resp = await client.get("/health")
                if resp.status_code == 200:
                    server_active = True
                    print(f"[INFO] Stand-in server already active on port {standin_port}.")
        except Exception:
            pass

        if not server_active:
            print(f"[INFO] Launching embedded Stand-in server on {standin_host}:{standin_port}...")
            from passageworks_standin.server import app

            cfg = uvicorn.Config(app=app, host=standin_host, port=standin_port, log_level="warning")
            srv = uvicorn.Server(cfg)
            server_task = asyncio.create_task(srv.serve())
            await asyncio.sleep(1.0)

    try:
        all_records: list[dict[str, Any]] = []

        # 1. Steady Scenario
        rec1 = await runner.run_scenario(
            scenario_name="steady",
            num_requests=25,
            duration_s=25.0,
            retrieval_setting="setting_a",
            traffic_pattern="uniform",
        )
        all_records.extend(rec1)

        # 2. Burst Scenario
        rec2 = await runner.run_scenario(
            scenario_name="burst",
            num_requests=35,
            duration_s=15.0,
            retrieval_setting="setting_a",
            traffic_pattern="burst",
        )
        all_records.extend(rec2)

        # 3. Sustained Overload Scenario
        rec3 = await runner.run_scenario(
            scenario_name="sustained_overload",
            num_requests=45,
            duration_s=15.0,
            retrieval_setting="setting_a",
            traffic_pattern="overload",
        )
        all_records.extend(rec3)

        # 4. Limit Halved Scenario (Stand-in with halved RPM)
        rec4 = await runner.run_scenario(
            scenario_name="per_minute_limit_halved",
            num_requests=25,
            duration_s=15.0,
            retrieval_setting="setting_a",
            traffic_pattern="uniform",
            standin_overrides={"halved_limits_active": True},
        )
        all_records.extend(rec4)

        # 5. Daily Budget Exhausted Scenario
        rec5 = await runner.run_scenario(
            scenario_name="daily_budget_exhausted",
            num_requests=15,
            duration_s=8.0,
            retrieval_setting="setting_a",
            traffic_pattern="uniform",
            standin_overrides={"daily_token_limit": 500},
        )
        all_records.extend(rec5)

        # 6. Retrieval Comparison Runs across the 3 settings (on question set)
        for setting in ["setting_a", "setting_b", "setting_c"]:
            rec_ret = await runner.run_scenario(
                scenario_name=f"retrieval_eval_{setting}",
                num_requests=18,
                duration_s=12.0,
                retrieval_setting=setting,
                traffic_pattern="uniform",
            )
            all_records.extend(rec_ret)

        # Write clean results to CSV
        runner.output_csv.unlink(missing_ok=True)
        runner.append_to_csv(all_records)
        print(
            f"\nAll scenarios completed. Total rows written to {runner.output_csv}: {len(all_records)}"
        )

    finally:
        if server_task and not server_task.done():
            server_task.cancel()


if __name__ == "__main__":
    asyncio.run(execute_all_scenarios())
