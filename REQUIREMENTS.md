# REQUIREMENTS.md — Requirements-to-Verification Matrix

## 1. Core Functional Requirements

| ID | Description | Source | Status | Verification Plan |
|---|---|---|---|---|
| **REQ-P1** | Pipeline in Python (pinned interpreter 3.13) | Brief p1 | In Progress | Automated environment check in CI |
| **REQ-P2** | Minimum 4 explicit pipeline steps | Brief p1 | Planned | `tests/test_pipeline.py`: trace step count >= 4 |
| **REQ-P3** | Real hosted model calls (Groq free tier) | Brief p1 | Planned | Calibration script against real endpoint |
| **REQ-P4** | Retrieval tool call (BM25 baseline) | Brief p1 | Planned | Unit test verifying tool execution in trace |
| **REQ-P5** | Branch or bounded loop | Brief p1 | Planned | Branch test (refusal) & loop test (verify-retry) |
| **REQ-P6** | Answers cite paper section/page | Brief p1 | Planned | Citation syntax regex + verification step |
| **REQ-P7** | Refusal on unanswerable questions | Brief p1 | Planned | Evaluation on negative question set |
| **REQ-P8** | Restricted library: exactly 3 arXiv papers | Brief p1 | Completed | Chunks extracted only from specified PDFs |

## 2. Library Document Specification

| Document | Identifier | Target Version | Status |
|---|---|---|---|
| Attention Is All You Need | arXiv:1706.03762 | Version 7 | Present (`1706.03762v7.pdf`) |
| Moshi: speech-text foundation model | arXiv:2410.00037 | Version 1 | Present (`Moshi 2410.00037v1.pdf`) |
| Dynamic Chunking for E2E Hierarchical Sequence Modeling | arXiv:2507.07955 | Version 2 | Present (`Dynamic Chunking...2507.07955v2.pdf`) |

*Note: Moshi v2 was removed from workspace to avoid ambiguity.*

## 3. Stand-in Service Requirements

| ID | Requirement | Verification Method |
|---|---|---|
| **REQ-S1** | Variable latency simulation | Parameterized latency tests |
| **REQ-S2** | Injected failure modes (429, 500, timeouts) | Unit tests against stand-in error routes |
| **REQ-S3** | Enforce RPM and daily token/request ceilings | Load harness rate limit verification |
| **REQ-S4** | Concurrency degradation under load | Stand-in concurrency stress test |
| **REQ-S5** | Chunked streaming output | SSE / chunk stream parser test |
| **REQ-S6** | Calibration against measured Groq telemetry | Calibration data comparison script |

## 4. Experimentation and Reporting

| ID | Requirement | Output Target |
|---|---|---|
| **REQ-E1** | Table 1: Real service limits & recovery | Report Section 2, Table 1 |
| **REQ-E2** | Table 2a: Latency across 5 scenarios | Report Section 3, Table 2a |
| **REQ-E3** | Table 2b: Outcomes across 5 scenarios | Report Section 3, Table 2b |
| **REQ-E4** | Table 3: 3 retrieval configurations on >=15 questions | Report Section 3, Table 3 |
| **REQ-E5** | Raw data output: `results.csv` with strict schema | `results/results.csv` validated by CI |
| **REQ-E6** | Trace deep-dive: 1 slow request dissected | Report Section 4 |
| **REQ-E7** | Failure case: 1 retry-makes-it-worse scenario | Report Section 6 |
| **REQ-E8** | Naive retrieval vulnerabilities: 3 concrete examples | Report Section "How this library will mislead" |
| **REQ-E9** | Daily exhaustion UX: Behavior at 3pm budget end | Report Section 7 |
| **REQ-E10**| Vaani product critique | Report Section "Your feedback on Vaani" |
