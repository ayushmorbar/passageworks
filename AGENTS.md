# AGENTS.md — Agent Collaboration Guidelines

## Project Identity
- **Project Name:** Passageworks
- **Sub-title:** A paper-grounded question-answering pipeline with measured behavior under load.
- **Reference Date:** November 2026 (Live research: 2026-11-09).
- **Core Mission:** Small, reliable, paper-grounded Q&A assistant evaluated under bursty traffic, provider limits, and service failures.

## Ground Rules for Agents & Contributors
1. **Source Boundaries:**
   - **Answer Evidence:** Strictly confined to the 3 exact arXiv papers:
     1. "Attention Is All You Need", arXiv 1706.03762v7
     2. "Moshi: a speech-text foundation model for real-time dialogue", arXiv 2410.00037v1
     3. "Dynamic Chunking for End-to-End Hierarchical Sequence Modeling", arXiv 2507.07955v2
   - **Engineering Research:** Official documentation (Groq, Python, FastAPI, etc.). Never leak engineering facts or external knowledge into paper-grounded answers.
2. **Citation Integrity:**
   - Every answer claim must be tied to `[Paper, Section, Page]`.
   - If the papers do not answer a question, the assistant must explicitly refuse to answer.
   - Validation checks claim-passage alignment; never rely on surface regex alone.
3. **Measurement Integrity:**
   - Use monotonic timing (`time.perf_counter()`).
   - Distinguish user-visible TTFT (including queue waiting) from provider TTFT.
   - Do not replace missing measurements with zero. Preserve blanks / nulls.
   - All table numbers must be directly computable from `results/results.csv`.
4. **Quota Consciousness:**
   - Real Groq free-tier tokens are scarce (~6,000 TPM, 100k-500k TPD).
   - Never run unmetered automated loops against real Groq.
   - CI tests must default to mock/stand-in mode with no credentials required.
5. **Human Approval:**
   - Request review before merging major architectural changes or initiating real-service load tests.
   - Do not perform destructive git commands or push external code without permission.

## Development & Test Commands
```powershell
# Run unit & mock integration tests (no Groq credentials needed)
pytest tests/ -v -m "not real_provider"

# Run linter & formatter
ruff check .
ruff format --check .

# Validate results CSV schema
python -m pytest tests/test_csv_schema.py

# Run Stand-in server locally
uvicorn passageworks_standin.server:app --port 8000
```
