"""Pipeline orchestrator: 4 steps, retrieval tool call, branch gating, and verification loop."""

import time
from typing import Optional, List

from relay.budget import TokenBudgetTracker
from relay.classify import CLASSIFIER_PROMPT, parse_classification_response
from relay.config import PipelineConfig, DEFAULT_CONFIG
from relay.draft import DRAFT_SYSTEM_PROMPT, format_evidence_context, extract_citations
from relay.groq_client import GroqClientWrapper
from relay.models import PipelineResult, PipelineStepEvent
from relay.queue import AdmissionController, QueueFullError, RequestTimeoutError
from relay.retrieve import RetrieverTool
from relay.verify import VERIFIER_PROMPT, parse_verification_response


class PassageworksPipeline:
    """End-to-end 4-step Q&A pipeline with branch gating and bounded revision loop."""

    def __init__(
        self,
        retriever: RetrieverTool,
        groq_client: GroqClientWrapper,
        budget: Optional[TokenBudgetTracker] = None,
        queue: Optional[AdmissionController] = None,
        config: PipelineConfig = DEFAULT_CONFIG,
    ):
        self.retriever = retriever
        self.client = groq_client
        self.budget = budget or TokenBudgetTracker()
        self.queue = queue or AdmissionController(
            max_concurrent=config.max_concurrent_requests,
            max_queue=config.max_queue_depth,
            deadline_s=config.request_deadline_seconds,
        )
        self.config = config

    async def execute(
        self,
        question: str,
        request_id: str,
        retrieval_setting: str = "setting_a",
    ) -> PipelineResult:
        """Run the full pipeline for a single user question."""
        overall_start = time.perf_counter()
        steps: List[PipelineStepEvent] = []
        total_retries = 0
        total_p_tokens = 0
        total_c_tokens = 0

        # Phase 0: Queue admission and concurrency gating
        try:
            _slot = await self.queue.acquire_slot()
        except QueueFullError:
            total_ms = (time.perf_counter() - overall_start) * 1000.0
            return PipelineResult(
                request_id=request_id,
                question=question,
                status="rate_limited",
                answer="Service overloaded: queue capacity exceeded.",
                is_refusal=True,
                citations=[],
                retrieved_chunks=[],
                steps=[],
                first_token_ms=None,
                total_ms=total_ms,
                retries=0,
                tokens_in=0,
                tokens_out=0,
                retrieval_setting=retrieval_setting,
                answer_grade="refused_correctly",
            )
        except RequestTimeoutError as rte:
            total_ms = (time.perf_counter() - overall_start) * 1000.0
            return PipelineResult(
                request_id=request_id,
                question=question,
                status="timeout",
                answer=str(rte),
                is_refusal=True,
                citations=[],
                retrieved_chunks=[],
                steps=[],
                first_token_ms=None,
                total_ms=total_ms,
                retries=0,
                tokens_in=0,
                tokens_out=0,
                retrieval_setting=retrieval_setting,
                answer_grade="refused_correctly",
            )

        try:
            # Phase 0b: Token budget ceiling check
            admitted, budget_err = self.budget.check_admission(estimated_tokens=800)
            if not admitted:
                total_ms = (time.perf_counter() - overall_start) * 1000.0
                return PipelineResult(
                    request_id=request_id,
                    question=question,
                    status="rate_limited",
                    answer=f"Request declined: {budget_err}",
                    is_refusal=True,
                    citations=[],
                    retrieved_chunks=[],
                    steps=[],
                    first_token_ms=None,
                    total_ms=total_ms,
                    retries=0,
                    tokens_in=0,
                    tokens_out=0,
                    retrieval_setting=retrieval_setting,
                    answer_grade="refused_correctly",
                )

            # Step 1: CLASSIFY (Branch Gating)
            step1_start = time.perf_counter()
            classify_resp = await self.client.chat_completion(
                model=self.config.classifier_model,
                messages=[
                    {"role": "system", "content": CLASSIFIER_PROMPT},
                    {"role": "user", "content": f"Query: {question}"},
                ],
                temperature=0.0,
                max_tokens=250,
            )
            step1_ms = (time.perf_counter() - step1_start) * 1000.0
            total_retries += classify_resp.retries_used
            total_p_tokens += classify_resp.prompt_tokens
            total_c_tokens += classify_resp.completion_tokens

            steps.append(
                PipelineStepEvent(
                    step_name="CLASSIFY",
                    start_time_ms=(step1_start - overall_start) * 1000.0,
                    duration_ms=step1_ms,
                    tokens_in=classify_resp.prompt_tokens,
                    tokens_out=classify_resp.completion_tokens,
                    details={"raw": classify_resp.content},
                )
            )

            decision = parse_classification_response(classify_resp.content)
            if not decision.is_in_scope:
                # Branch: Refuse immediately
                total_ms = (time.perf_counter() - overall_start) * 1000.0
                self.budget.record_usage(total_p_tokens, total_c_tokens)
                return PipelineResult(
                    request_id=request_id,
                    question=question,
                    status="ok",
                    answer=decision.refusal_message or "Question outside permitted paper library.",
                    is_refusal=True,
                    citations=[],
                    retrieved_chunks=[],
                    steps=steps,
                    first_token_ms=total_ms,
                    total_ms=total_ms,
                    retries=total_retries,
                    tokens_in=total_p_tokens,
                    tokens_out=total_c_tokens,
                    retrieval_setting=retrieval_setting,
                    answer_grade="refused_correctly",
                )

            # Step 2: RETRIEVE (Tool Call)
            step2_start = time.perf_counter()
            retrieval_res = self.retriever.retrieve(question, setting=retrieval_setting)
            step2_ms = (time.perf_counter() - step2_start) * 1000.0
            retrieved_chunks = [r.chunk for r in retrieval_res]

            steps.append(
                PipelineStepEvent(
                    step_name="RETRIEVE",
                    start_time_ms=(step2_start - overall_start) * 1000.0,
                    duration_ms=step2_ms,
                    tokens_in=0,
                    tokens_out=0,
                    details={"chunks_fetched": len(retrieved_chunks), "setting": retrieval_setting},
                )
            )

            if not retrieved_chunks:
                total_ms = (time.perf_counter() - overall_start) * 1000.0
                return PipelineResult(
                    request_id=request_id,
                    question=question,
                    status="ok",
                    answer="No relevant passages could be retrieved from the three papers.",
                    is_refusal=True,
                    citations=[],
                    retrieved_chunks=[],
                    steps=steps,
                    first_token_ms=total_ms,
                    total_ms=total_ms,
                    retries=total_retries,
                    tokens_in=total_p_tokens,
                    tokens_out=total_c_tokens,
                    retrieval_setting=retrieval_setting,
                    answer_grade="refused_correctly",
                )

            # Step 3: DRAFT (Synthesize cited answer)
            context_block = format_evidence_context(retrieved_chunks)
            draft_messages = [
                {"role": "system", "content": DRAFT_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"EVIDENCE EXCERPTS:\n{context_block}\n\nQUESTION: {question}\n\nAnswer with inline citations:",
                },
            ]

            step3_start = time.perf_counter()
            draft_resp = await self.client.chat_completion(
                model=self.config.primary_model,
                messages=draft_messages,
                temperature=0.0,
                max_tokens=600,
            )
            step3_ms = (time.perf_counter() - step3_start) * 1000.0
            total_retries += draft_resp.retries_used
            total_p_tokens += draft_resp.prompt_tokens
            total_c_tokens += draft_resp.completion_tokens

            steps.append(
                PipelineStepEvent(
                    step_name="DRAFT",
                    start_time_ms=(step3_start - overall_start) * 1000.0,
                    duration_ms=step3_ms,
                    tokens_in=draft_resp.prompt_tokens,
                    tokens_out=draft_resp.completion_tokens,
                    details={"text": draft_resp.content},
                )
            )

            current_answer = draft_resp.content
            citations = extract_citations(current_answer)

            # Step 4: VERIFY with Bounded Revision Loop (max 2 loops)
            max_revisions = 2
            loop_idx = 0
            is_verified = False

            while loop_idx <= max_revisions:
                step4_start = time.perf_counter()
                verifier_messages = [
                    {"role": "system", "content": VERIFIER_PROMPT},
                    {
                        "role": "user",
                        "content": f"EVIDENCE:\n{context_block}\n\nDRAFT ANSWER TO VERIFY:\n{current_answer}",
                    },
                ]
                verify_resp = await self.client.chat_completion(
                    model=self.config.primary_model,
                    messages=verifier_messages,
                    temperature=0.0,
                    max_tokens=350,
                )
                step4_ms = (time.perf_counter() - step4_start) * 1000.0
                total_retries += verify_resp.retries_used
                total_p_tokens += verify_resp.prompt_tokens
                total_c_tokens += verify_resp.completion_tokens

                outcome = parse_verification_response(verify_resp.content, citations)
                steps.append(
                    PipelineStepEvent(
                        step_name=f"VERIFY_LOOP_{loop_idx}",
                        start_time_ms=(step4_start - overall_start) * 1000.0,
                        duration_ms=step4_ms,
                        tokens_in=verify_resp.prompt_tokens,
                        tokens_out=verify_resp.completion_tokens,
                        details={
                            "is_valid": outcome.is_valid,
                            "unsupported": outcome.unsupported_claims,
                        },
                    )
                )

                if outcome.is_valid:
                    is_verified = True
                    break

                # If invalid and loops remaining, re-draft with feedback
                loop_idx += 1
                if loop_idx <= max_revisions:
                    redraft_start = time.perf_counter()
                    revision_prompt = (
                        f"Your previous answer had unsupported claims: {outcome.unsupported_claims}. "
                        f"Guidance: {outcome.suggested_revision}. "
                        f"Rewrite the answer strictly using ONLY the evidence, or state that evidence is insufficient."
                    )
                    draft_messages.append({"role": "assistant", "content": current_answer})
                    draft_messages.append({"role": "user", "content": revision_prompt})

                    revised_resp = await self.client.chat_completion(
                        model=self.config.primary_model,
                        messages=draft_messages,
                        temperature=0.0,
                        max_tokens=500,
                    )
                    redraft_ms = (time.perf_counter() - redraft_start) * 1000.0
                    total_retries += revised_resp.retries_used
                    total_p_tokens += revised_resp.prompt_tokens
                    total_c_tokens += revised_resp.completion_tokens

                    steps.append(
                        PipelineStepEvent(
                            step_name=f"REVISE_LOOP_{loop_idx}",
                            start_time_ms=(redraft_start - overall_start) * 1000.0,
                            duration_ms=redraft_ms,
                            tokens_in=revised_resp.prompt_tokens,
                            tokens_out=revised_resp.completion_tokens,
                            details={"revised_text": revised_resp.content},
                        )
                    )
                    current_answer = revised_resp.content
                    citations = extract_citations(current_answer)

            # End of verification loop
            total_ms = (time.perf_counter() - overall_start) * 1000.0
            self.budget.record_usage(total_p_tokens, total_c_tokens)

            # If verification failed even after max revisions, safely refuse
            if not is_verified:
                return PipelineResult(
                    request_id=request_id,
                    question=question,
                    status="ok",
                    answer="The provided paper excerpts do not contain sufficient verified evidence to support a factual answer.",
                    is_refusal=True,
                    citations=[],
                    retrieved_chunks=retrieved_chunks,
                    steps=steps,
                    first_token_ms=total_ms,
                    total_ms=total_ms,
                    retries=total_retries,
                    tokens_in=total_p_tokens,
                    tokens_out=total_c_tokens,
                    retrieval_setting=retrieval_setting,
                    answer_grade="refused_correctly",
                )

            # Release verified answer
            return PipelineResult(
                request_id=request_id,
                question=question,
                status="ok",
                answer=current_answer,
                is_refusal=False,
                citations=citations,
                retrieved_chunks=retrieved_chunks,
                steps=steps,
                first_token_ms=total_ms,  # Buffered output released after verification
                total_ms=total_ms,
                retries=total_retries,
                tokens_in=total_p_tokens,
                tokens_out=total_c_tokens,
                retrieval_setting=retrieval_setting,
                answer_grade="correct",
            )

        finally:
            self.queue.release_slot()
