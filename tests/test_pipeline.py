"""Unit and integration tests for Passageworks 4-step pipeline."""

from pathlib import Path

import pytest

from relay.budget import TokenBudgetTracker
from relay.config import PipelineConfig
from relay.groq_client import LLMCallResult
from relay.pipeline import PassageworksPipeline
from relay.queue import AdmissionController
from relay.retrieve import RetrieverTool


class MockLLMClient:
    """Mock client simulating Groq/Stand-in responses for fast deterministic CI testing."""

    def __init__(self, classify_in_scope: bool = True, verify_valid: bool = True):
        self.classify_in_scope = classify_in_scope
        self.verify_valid = verify_valid
        self.call_history = []

    async def chat_completion(self, model, messages, temperature=0.0, max_tokens=800):
        self.call_history.append((model, messages))
        prompt_str = " ".join(str(m.get("content", "")) for m in messages)

        # 1. Classification
        if "scope gatekeeper" in prompt_str:
            if self.classify_in_scope:
                content = '{"is_in_scope": true, "relevant_paper": "attention", "reason": "Query about transformers."}'
            else:
                content = (
                    '{"is_in_scope": false, "relevant_paper": "none", "reason": "Unrelated topic."}'
                )
            return LLMCallResult(
                content=content,
                prompt_tokens=50,
                completion_tokens=25,
                total_tokens=75,
                first_token_ms=50.0,
                total_call_ms=80.0,
                retries_used=0,
            )

        # 2. Verification
        if "Fact Verification Auditor" in prompt_str:
            if self.verify_valid:
                content = '{"is_valid": true, "unsupported_claims": [], "suggested_revisions": ""}'
            else:
                content = '{"is_valid": false, "unsupported_claims": ["claim X not found"], "suggested_revisions": "remove claim X"}'
            return LLMCallResult(
                content=content,
                prompt_tokens=150,
                completion_tokens=30,
                total_tokens=180,
                first_token_ms=40.0,
                total_call_ms=90.0,
                retries_used=0,
            )

        # 3. Drafting / Revision
        draft_text = (
            "The Transformer relies entirely on self-attention mechanisms without recurrence "
            "[Attention Is All You Need, Abstract, p.1]."
        )
        return LLMCallResult(
            content=draft_text,
            prompt_tokens=250,
            completion_tokens=40,
            total_tokens=290,
            first_token_ms=60.0,
            total_call_ms=120.0,
            retries_used=0,
        )


@pytest.fixture
def retriever():
    chunks_path = Path("papers/chunks.jsonl")
    return RetrieverTool(chunks_path)


@pytest.mark.asyncio
async def test_pipeline_nominal_flow(retriever):
    mock_client = MockLLMClient(classify_in_scope=True, verify_valid=True)
    pipeline = PassageworksPipeline(
        retriever=retriever,
        groq_client=mock_client,
        budget=TokenBudgetTracker(),
        queue=AdmissionController(max_concurrent=2, max_queue=5),
        config=PipelineConfig(),
    )

    result = await pipeline.execute(
        question="How does self-attention work in Transformer?",
        request_id="req-test-001",
        retrieval_setting="setting_a",
    )

    assert result.status == "ok"
    assert result.is_refusal is False
    assert result.answer_grade == "correct"
    assert len(result.citations) >= 1
    assert result.citations[0].paper_title == "Attention Is All You Need"
    assert result.citations[0].page == 1

    # Verify minimum 4 steps: CLASSIFY, RETRIEVE, DRAFT, VERIFY
    step_names = [s.step_name for s in result.steps]
    assert "CLASSIFY" in step_names
    assert "RETRIEVE" in step_names
    assert "DRAFT" in step_names
    assert any("VERIFY" in s for s in step_names)
    assert len(result.steps) >= 4


@pytest.mark.asyncio
async def test_pipeline_out_of_scope_branch(retriever):
    mock_client = MockLLMClient(classify_in_scope=False)
    pipeline = PassageworksPipeline(
        retriever=retriever,
        groq_client=mock_client,
        budget=TokenBudgetTracker(),
        queue=AdmissionController(max_concurrent=2, max_queue=5),
    )

    result = await pipeline.execute(
        question="How do I bake chocolate cake?",
        request_id="req-test-002",
    )

    assert result.status == "ok"
    assert result.is_refusal is True
    assert result.answer_grade == "refused_correctly"
    assert "restricted library" in result.answer
    # Should only execute CLASSIFY step before branch refusal
    assert len(result.steps) == 1
    assert result.steps[0].step_name == "CLASSIFY"


@pytest.mark.asyncio
async def test_pipeline_verification_loop(retriever):
    # Verifier initially rejects, triggering bounded revision loop
    mock_client = MockLLMClient(classify_in_scope=True, verify_valid=False)
    pipeline = PassageworksPipeline(
        retriever=retriever,
        groq_client=mock_client,
        budget=TokenBudgetTracker(),
        queue=AdmissionController(max_concurrent=2, max_queue=5),
    )

    result = await pipeline.execute(
        question="What is the Transformer architecture?",
        request_id="req-test-003",
    )

    # After max 2 revisions fail verification, pipeline safely refuses
    assert result.status == "ok"
    assert result.is_refusal is True
    assert result.answer_grade == "refused_correctly"

    # Step count should include multiple verify and revise steps
    step_names = [s.step_name for s in result.steps]
    assert "VERIFY_LOOP_0" in step_names
    assert "REVISE_LOOP_1" in step_names
    assert "VERIFY_LOOP_1" in step_names
    assert len(result.steps) >= 6
