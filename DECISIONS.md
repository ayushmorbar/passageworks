# DECISIONS.md — Architectural Decision Log (ADR)

## ADR-001: Project Name & Identity
- **Date:** 2026-11-09
- **Decision:** Name the project **Passageworks** (subtitled: *A paper-grounded question-answering pipeline with measured behavior under load*).
- **Rationale:** Focuses on the architectural reality of finding, verifying, and routing passages from technical literature through a constrained multi-stage pipeline.

## ADR-002: Restricted Library Versioning
- **Date:** 2026-11-09
- **Decision:** Restrict document corpus exclusively to:
  - Attention Is All You Need (1706.03762v7)
  - Moshi (2410.00037v1)
  - Dynamic Chunking (2507.07955v2)
  Moshi v2 was removed from the active directory to prevent accidental inclusion or citation drift.
- **Consequences:** Any question requiring information outside these exact versions must be safely refused.

## ADR-003: Output Buffering vs Streaming for Answers
- **Date:** 2026-11-09
- **Decision:** User-visible answers will be buffered and released only after claim verification passes. Progress markers (e.g. `event: retrieving`, `event: drafting`) may be emitted as SSE status, but token stream release is gated by verification.
- **Rationale:** Gaining 200ms in TTFT by streaming raw generated tokens is unacceptable if the system hallucinates an unsupported claim or invalid citation before failing verification.

## ADR-004: Pipeline State Machine & Branching
- **Date:** 2026-11-09
- **Decision:** A 4-step pipeline:
  1. `CLASSIFY` (fast classifier: check query relevance & answerability) -> branch: REFUSE or CONTINUE
  2. `RETRIEVE` (BM25 tool call against indexed paper passages)
  3. `DRAFT` (LLM synthesizes cited response from retrieved context)
  4. `VERIFY` (LLM checks claim-evidence alignment) -> bounded loop: REVISE (max 2 iterations) or EMIT
- **Rationale:** Fulfills all brief requirements (>=4 steps, tool call, branch, loop) with minimal token overhead.

## ADR-005: Model Allocation Strategy (Groq Free Tier)
- **Date:** 2026-11-09
- **Decision:**
  - Allocate lighter model (`llama-3.1-8b-instant`) for `CLASSIFY` (500k TPD, 14,400 RPD budget).
  - Allocate larger model (`llama-3.3-70b-versatile` or `qwen/qwen3-32b`) for `DRAFT` and `VERIFY`.
- **Rationale:** Free-tier TPM on Groq (~6,000 TPM) is the primary bottleneck. Spreading pipeline stages across independent model quotas avoids burning the 70B token allocation on simple classification.
