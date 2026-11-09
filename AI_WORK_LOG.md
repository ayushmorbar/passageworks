# AI_WORK_LOG.md — Honest AI Collaboration Log

## Milestone 0: Initialization & Planning (2026-11-09)

### 1. Key Prompts and User Directives
- **Initial Request:** Systems-engineering mentor for "The Relay" assignment. Required strict adherence to brief, real vs stand-in evaluation, 2-page report structure, verification matrix, and live date currentness.
- **Correction by User:** Explicitly instructed that research date is November 2026 (not 2025).
- **Decisions Communicated by User:**
  - Project name updated to **Passageworks**.
  - Moshi v2 deleted from workspace; only Moshi v1 retained.
  - Groq API key is ready.
  - Assignment received today (2026-11-09) approx noon -> 4-day deadline set to 2026-11-13 12:00.
  - Requested GitHub repo with CI and local git.
  - Instructed to install `uv` on Miniconda environment.

### 2. Discovered Realities & Corrections Caught
- **Date Correction:** Antigravity initially drafted research under 2025 timestamp. User promptly flagged this; all provider schemas, SDK versions (Groq 1.7.0, FastAPI 0.162.2, uv 0.13.7) and dates updated to November 2026.
- **Quota Reality Check:** Live docs show free-tier Groq has dynamic TPM of ~6,000, meaning tokens-per-minute (not RPM) is the true hard constraint for multi-step pipelines.
- **Document Hygiene:** Verified absence of Moshi v2 in local directory.

### 3. Decisions Overruled / Modified
- *Initial Proposal:* Stream answer tokens to optimize user-visible TTFT.
- *Overruled by Design:* Buffered output selected to ensure every claim is checked by the `VERIFY` step before user exposure.

## Milestone 2 & 3: Pipeline Core & Stand-in Service (2026-11-09)
- **Implemented:**
  - `src/relay/budget.py`: Sliding window TPM/RPM tracking and daily token/request ceilings.
  - `src/relay/queue.py`: Concurrency limiting (max 3), queue backlog rejection (depth 50), and deadline monitoring.
  - `src/relay/groq_client.py`: AsyncGroq wrapper with application-level exponential backoff + jitter and rate-limit header extraction.
  - `src/relay/pipeline.py`: Complete 4-step pipeline (CLASSIFY -> branch -> RETRIEVE -> DRAFT -> VERIFY -> bounded revision loop -> release answer).
  - `src/relay_standin/server.py`: Stand-in FastAPI service simulating Groq API with configurable TTFT, streaming chunks, slowdown under load, and rate limit injection.
- **Verification:**
  - 21 unit & integration tests passing in `tests/`.
  - All code formatted and clean under Ruff.
  - Local commit `803c824` created.
