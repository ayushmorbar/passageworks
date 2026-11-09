"""Run genuine real-service evaluation against live Groq API and capture rows for results.csv.

Paced to respect free-tier TPM (8,000) limits with sub-second token replenishment.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness.calibrate_groq import load_env_local
from harness.load_runner import grade_answer
from passageworks.config import PipelineConfig
from passageworks.groq_client import GroqClientWrapper
from passageworks.pipeline import PassageworksPipeline
from passageworks.retrieve import RetrieverTool

REAL_QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "q01",
        "paper": "attention",
        "is_answerable": True,
        "question": "What is the formula for Scaled Dot-Product Attention in the Transformer?",
        "expected_evidence": "Attention(Q, K, V) = softmax(QK^T / sqrt(d_k))V",
        "expected_citation": "Section 3.2.1, p.4",
        "setting": "setting_b",
    },
    {
        "id": "q05",
        "paper": "moshi",
        "is_answerable": True,
        "question": "What is the neural audio codec used by Moshi, and what is its frame rate and bitrate?",
        "expected_evidence": "Mimi codec, operating at 12.5 Hz frame rate with 32 residual vector quantizers at 1.1 kbps.",
        "expected_citation": "Section 2, Section 3.1, p.3, p.5",
        "setting": "setting_b",
    },
    {
        "id": "q09",
        "paper": "dynamic_chunking",
        "is_answerable": True,
        "question": "What core problem does Dynamic Chunking address in hierarchical sequence modeling?",
        "expected_evidence": "Dynamic segmentation of sequences without relying on fixed heuristic boundaries.",
        "expected_citation": "Abstract, Section 1, p.1, p.2",
        "setting": "setting_b",
    },
    {
        "id": "q17",
        "paper": "attention",
        "is_answerable": True,
        "question": "What positional encoding formulation is used in Attention Is All You Need?",
        "expected_evidence": "Sinusoidal functions of different frequencies.",
        "expected_citation": "Section 3.5, p.6",
        "setting": "setting_b",
    },
    {
        "id": "q04",
        "paper": "attention",
        "is_answerable": False,
        "question": "What learning rate schedule was used to train the Transformer on the ImageNet dataset?",
        "expected_evidence": "Unanswerable: The paper only trains on machine translation and constituency parsing, not ImageNet.",
        "expected_citation": "N/A - Must refuse",
        "setting": "setting_b",
    },
    {
        "id": "q16",
        "paper": "none",
        "is_answerable": False,
        "question": "How do you calculate the optimal temperature parameter for annealing in reinforcement learning from human feedback?",
        "expected_evidence": "Unanswerable: General RLHF theory is not discussed in the three papers.",
        "expected_citation": "N/A - Must refuse",
        "setting": "setting_b",
    },
]


async def run_real_evaluation() -> list[dict[str, Any]]:
    """Execute real-provider benchmark against live Groq API."""
    env = load_env_local()
    api_key = env.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
    if not api_key:
        print("[ERROR] GROQ_API_KEY not found in .env.local or environment.")
        return []

    config = PipelineConfig(
        groq_api_key=api_key,
        groq_base_url=None,
        fast_fail_lockout_seconds=10.0,
        max_retries=2,
    )
    client = GroqClientWrapper(api_key=api_key, base_url=None, max_retries=2)
    retriever = RetrieverTool(Path("papers/chunks.jsonl"))
    pipeline = PassageworksPipeline(config=config, groq_client=client, retriever=retriever)

    records: list[dict[str, Any]] = []
    trace_records: list[dict[str, Any]] = []

    print("=======================================================")
    print("Starting Real-Service Benchmark (Live Groq API)")
    print(f"Questions: {len(REAL_QUESTIONS)} | Model: {config.primary_model}")
    print("=======================================================")

    for i, q_meta in enumerate(REAL_QUESTIONS):
        req_id = f"real-groq-{i + 1:04d}"
        start_iso = datetime.now(UTC).isoformat()
        q_text = q_meta["question"]
        setting = q_meta["setting"]

        print(f"\n[{i + 1}/{len(REAL_QUESTIONS)}] Dispatching {req_id}: '{q_text[:50]}...'")

        res = await pipeline.execute(
            question=q_text,
            request_id=req_id,
            retrieval_setting=setting,
        )

        grade = grade_answer(q_meta, res)
        print(
            f"    -> Status: {res.status} | Grade: {grade} | TTFT: {res.first_token_ms}ms | Total: {res.total_ms:.1f}ms"
        )
        print(
            f"    -> Tokens in: {res.tokens_in} | out: {res.tokens_out} | Citations: {len(res.citations)}"
        )

        row = {
            "request_id": req_id,
            "scenario": "real_service",
            "source": "real",
            "start_time": start_iso,
            "first_token_ms": f"{res.first_token_ms:.1f}" if res.first_token_ms is not None else "",
            "total_ms": f"{res.total_ms:.1f}",
            "status": res.status,
            "retries": res.retries,
            "tokens_in": res.tokens_in,
            "tokens_out": res.tokens_out,
            "retrieval_setting": setting,
            "answer_grade": grade,
        }
        records.append(row)

        trace_records.append(
            {
                "request_id": req_id,
                "start_time": start_iso,
                "question": q_text,
                "answer": res.answer,
                "citations": [c.raw_citation for c in res.citations],
                "status": res.status,
                "first_token_ms": res.first_token_ms,
                "total_ms": res.total_ms,
                "tokens_in": res.tokens_in,
                "tokens_out": res.tokens_out,
                "retries": res.retries,
                "retrieval_setting": setting,
                "step_events": [
                    {
                        "step_name": e.step_name,
                        "duration_ms": e.duration_ms,
                        "tokens_in": e.tokens_in,
                        "tokens_out": e.tokens_out,
                        "details": e.details,
                    }
                    for e in res.steps
                ],
            }
        )

        # Conservative 8s delay between requests to preserve 8,000 TPM rolling budget
        if i < len(REAL_QUESTIONS) - 1:
            print("    -> Pacing delay: 8s...")
            await asyncio.sleep(8.0)

    # Save real traces
    trace_dir = Path("results/traces")
    trace_dir.mkdir(parents=True, exist_ok=True)
    with open(trace_dir / "real_service_traces.jsonl", "w", encoding="utf-8") as f:
        for t in trace_records:
            f.write(json.dumps(t) + "\n")

    return records


if __name__ == "__main__":
    records = asyncio.run(run_real_evaluation())
    print(f"\nCompleted {len(records)} real requests.")
