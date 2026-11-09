"""Open-loop load harness executing the 5 mandatory scenarios and generating results.csv."""

import asyncio
import csv
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

import httpx

from relay.budget import TokenBudgetTracker
from relay.groq_client import GroqClientWrapper
from relay.models import PipelineResult
from relay.pipeline import PassageworksPipeline
from relay.queue import AdmissionController
from relay.retrieve import RetrieverTool


def load_questions() -> List[Dict[str, Any]]:
    path = Path("harness/questions.jsonl")
    questions = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                questions.append(json.loads(line.strip()))
    return questions


def grade_answer(q_meta: Dict[str, Any], result: PipelineResult) -> str:
    """Determine answer grade category required by brief."""
    is_answerable = q_meta.get("is_answerable", True)

    if result.status != "ok":
        # Rate limited or timed out requests did not produce answers
        return "refused_correctly" if not is_answerable else "wrong"

    if result.is_refusal:
        return "refused_correctly" if not is_answerable else "refused_wrongly"

    # Not a refusal: if it was unanswerable but answered -> wrong (hallucination)
    if not is_answerable:
        return "wrong"

    # Answerable question: check if citations exist
    if result.citations:
        return "correct"
    return "wrong"


class LoadScenarioRunner:
    """Executes open-loop arrival schedules against Stand-in or Real provider."""

    def __init__(
        self,
        retriever: RetrieverTool,
        source: str = "stand-in",
        base_url: str = "http://127.0.0.1:8000/v1",
        output_csv: Path = Path("results/results.csv"),
    ):
        self.retriever = retriever
        self.source = source
        self.base_url = base_url
        self.output_csv = output_csv
        self.questions = load_questions()

    async def _configure_standin(self, config_params: Dict[str, Any]) -> None:
        """Call Stand-in control endpoint to adjust limits or latency."""
        try:
            async with httpx.AsyncClient(base_url="http://127.0.0.1:8000", timeout=5.0) as client:
                await client.post("/control/reset")
                await client.post("/control/configure", json=config_params)
        except Exception:
            pass  # When testing in-memory or real service

    async def run_scenario(
        self,
        scenario_name: str,
        num_requests: int,
        duration_s: float,
        retrieval_setting: str = "setting_a",
        traffic_pattern: str = "uniform",  # uniform, burst, overload
        standin_overrides: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Run an open-loop arrival sequence."""
        print("\n=======================================================")
        print(f"Starting Scenario: {scenario_name} ({self.source})")
        print(
            f"Requests: {num_requests} | Duration: {duration_s}s | Target Rate: {num_requests / (duration_s / 60):.1f} req/min"
        )
        print("=======================================================")

        if self.source == "stand-in":
            await self._configure_standin(standin_overrides or {})

        # Initialize pipeline instance
        groq_client = GroqClientWrapper(
            base_url=self.base_url if self.source == "stand-in" else None,
            default_timeout=15.0,
            max_retries=2,
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
        queue = AdmissionController(max_concurrent=3, max_queue=25, deadline_s=25.0)

        pipeline = PassageworksPipeline(
            retriever=self.retriever,
            groq_client=groq_client,
            budget=budget,
            queue=queue,
        )

        # Precompute planned dispatch offsets (open-loop schedule)
        planned_offsets: List[float] = []
        if traffic_pattern == "burst":
            # Normal rate for first 20%, sudden spike in middle, then decay
            for i in range(num_requests):
                if i < int(num_requests * 0.2):
                    planned_offsets.append(random.uniform(0.0, duration_s * 0.25))
                elif i < int(num_requests * 0.7):
                    planned_offsets.append(
                        random.uniform(duration_s * 0.25, duration_s * 0.45)
                    )  # Intense spike
                else:
                    planned_offsets.append(random.uniform(duration_s * 0.45, duration_s))
            planned_offsets.sort()
        elif traffic_pattern == "overload":
            # Continuous rapid arrival rate
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

        records: List[Dict[str, Any]] = []
        active_tasks = []
        start_clock = time.perf_counter()

        async def worker(req_idx: int, q_data: Dict[str, Any]):
            req_id = f"req-{scenario_name[:3]}-{req_idx + 1:04d}"
            start_iso = datetime.now(timezone.utc).isoformat()
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

        # Dispatch requests according to open-loop timetable
        for i, planned_offset in enumerate(planned_offsets):
            now_elapsed = time.perf_counter() - start_clock
            delay = planned_offset - now_elapsed
            if delay > 0:
                await asyncio.sleep(delay)

            q_data = self.questions[i % len(self.questions)]
            task = asyncio.create_task(worker(i, q_data))
            active_tasks.append(task)

        # Wait for all in-flight requests to settle
        await asyncio.gather(*active_tasks, return_exceptions=True)

        print(f"Completed Scenario: {scenario_name}. Recorded {len(records)} requests.")
        return records

    def append_to_csv(self, records: List[Dict[str, Any]]) -> None:
        """Append rows to results.csv with correct schema."""
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

        with open(self.output_csv, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            for r in records:
                writer.writerow(r)


async def execute_all_scenarios(source: str = "stand-in"):
    chunks_path = Path("papers/chunks.jsonl")
    retriever = RetrieverTool(chunks_path)
    runner = LoadScenarioRunner(retriever=retriever, source=source)

    # If targeting stand-in, auto-start in-process uvicorn server if not already running on port 8000
    server_task = None
    if source == "stand-in":
        try:
            async with httpx.AsyncClient(timeout=1.0) as test_client:
                await test_client.get("http://127.0.0.1:8000/docs")
                print("[INFO] Stand-in server already active on port 8000.")
        except Exception:
            import uvicorn
            from relay_standin.server import app as standin_app

            print("[INFO] Launching embedded Stand-in server on 127.0.0.1:8000...")
            cfg = uvicorn.Config(standin_app, host="127.0.0.1", port=8000, log_level="warning")
            srv = uvicorn.Server(cfg)
            server_task = asyncio.create_task(srv.serve())
            await asyncio.sleep(1.0)

    try:
        all_records = []

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
                num_requests=18,  # all 18 authored questions
                duration_s=12.0,
                retrieval_setting=setting,
                traffic_pattern="uniform",
            )
            all_records.extend(rec_ret)

        # Save all to results.csv
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
