# Passageworks

> **A paper-grounded question-answering pipeline with measured behavior under load.**

Passageworks is an engineering study and implementation of a multi-stage research-paper Q&A assistant evaluated under bursty traffic, provider rate limits, and service degradations.

---

## 1. System Overview

Passageworks answers technical questions strictly grounded in three research papers:
1. **Attention Is All You Need** (`arXiv:1706.03762v7`)
2. **Moshi: a speech-text foundation model for real-time dialogue** (`arXiv:2410.00037v1`)
3. **Dynamic Chunking for End-to-End Hierarchical Sequence Modeling** (`arXiv:2507.07955v2`)

The assistant employs a four-step pipeline with an explicit retrieval tool call, branch gating, and a bounded verification loop:
- **Step 1: CLASSIFY** — Distinguishes in-scope, answerable queries from out-of-scope or unanswerable queries. Gates execution or safely refuses.
- **Step 2: RETRIEVE** — Executes a BM25 retrieval tool across pre-indexed passage chunks with page and section metadata.
- **Step 3: DRAFT** — Synthesizes a factual reply incorporating strict `[Paper, Section, Page]` citations.
- **Step 4: VERIFY** — Validates claim-evidence support. If unsupported claims exist, triggers a bounded revision loop (max 2 attempts) before releasing buffered output or falling back to safe refusal.

---

## 2. Quickstart & Installation

### Requirements
- Python 3.13+
- `uv` package manager (or `pip`)

```powershell
# Sync locked dependencies
uv sync

# Or install editable package
pip install -e .
```

---

## 3. Running the Tests & Stand-in

```powershell
# Run CI unit tests (no external API credentials needed)
pytest tests/ -v -m "not real_provider"

# Run the Stand-in model server locally
uvicorn relay_standin.server:app --host 127.0.0.1 --port 8000
```

---

## 4. Running Experiments

```powershell
# Calibrate real Groq telemetry (quota-conscious, requires GROQ_API_KEY)
python -m harness.calibrate_groq

# Run load evaluation across the 5 mandatory scenarios
python -m harness.load_runner --scenario steady
python -m harness.load_runner --scenario burst
python -m harness.load_runner --scenario sustained_overload
python -m harness.load_runner --scenario limit_halved
python -m harness.load_runner --scenario daily_exhausted

# Generate results tables from results.csv
python -m analysis.tables
```

---

## 5. Repository Structure
- `src/relay/` — Core pipeline orchestration, stages (classify, retrieve, draft, verify), budget & queue.
- `src/relay_standin/` — Stand-in mock service with controllable latency, failure injection, and limits.
- `papers/` — Chunks and extracted metadata from the 3 arXiv papers.
- `harness/` — Open-loop load generator and question battery.
- `analysis/` — Table generators and trace breakdown utilities.
- `results/` — `results.csv` and JSONL trace archives.
- `tests/` — Test suite including CSV schema validation.
