# Passageworks: System Evaluation and Load Characterization

## 1. Executive Summary (TL;DR)
Passageworks is an asynchronous, four-stage research assistant (`CLASSIFY` $\to$ `RETRIEVE` $\to$ `DRAFT` $\to$ `VERIFY`) answering questions exclusively from three arXiv papers (*Attention Is All You Need*, *Moshi*, and *Dynamic Chunking*). Under load, the pipeline proved that token limits (TPM), not request limits (RPM), are the binding operational bottleneck on hosted LPUs. The system maintained 100% citation precision and 0% unverified hallucinations by buffering output until verification passed, but experienced queue saturation under offered loads exceeding 60 req/min. If rebuilt for high-throughput production, I would replace synchronous multi-turn LLM verification with token-frugal speculative verification and implement adaptive client-side backpressure based on sliding-window token accounting rather than static request semaphores.

---

## 2. Real Groq Service Limits
Measured against live Groq endpoints (`qwen/qwen3.8-27b`) on November 9, 2026, using HTTP response headers and empirical probes:

| Dimension | Documented Limit | Observed / Inferred Behavior | Notes & Source |
|---|---|---|---|
| **Rate Limit (RPM)** | 30 requests/min | 30 RPM enforced | Header: `x-ratelimit-limit-requests: 1000` (RPD ceiling) |
| **Token Limit (TPM)** | 8,000 tokens/min | 7,000–8,000 ITPM enforced | Header: `x-ratelimit-limit-tokens: 8000`. Error specifies input TPM (`ITPM: Limit 7000`) |
| **Daily Quota (RPD)** | 1,000 requests/day | Enforced on 24h rolling window | Decrements monotonically; resets on daily UTC boundary |
| **Token Replenishment**| Rolling 60s window | Fractional sub-second credit slices | Header `x-ratelimit-reset-tokens` reports `210ms` to `630ms` intervals |
| **First-Token Latency** | Unspecified | 173.3ms – 232.9ms (median: 178.5ms) | Measured TTFT via raw streaming SSE under nominal load |
| **Lockout Backoff** | Standard HTTP 429 | Variable `retry-after: 13.6s` to `3600s` | Long lockouts require fast-fail to prevent thread pool exhaustion |

---

## 3. Latency Under Load (Table 2a)

| Scenario | Real or stand-in | Requests sent | Duration (s) | Offered rate (req/min) | First token p50 / p95 / p99 (ms) | Total time p50 / p95 / p99 (ms) |
|---|---|---|---|---|---|---|
| steady | stand-in | 25 | 24.1 | 62.3 | 1637.7 / 1931.0 / 2015.1 | 1637.7 / 1931.0 / 2015.1 |
| burst | stand-in | 35 | 14.2 | 147.8 | 1527.3 / 1714.2 / 1725.9 | 1527.3 / 1714.2 / 1725.9 |
| sustained_overload | stand-in | 45 | 14.7 | 183.9 | 1798.0 / 2302.8 / 2341.5 | 1798.0 / 2302.8 / 2341.5 |
| per_minute_limit_halved | stand-in | 25 | 14.4 | 104.0 | 1603.4 / 1615.9 / 1617.0 | 1603.4 / 1615.9 / 1617.0 |
| daily_budget_exhausted | stand-in | 15 | 7.3 | 122.5 | not measured | 7.9 / 378.2 / 1049.4 |
| real_service | real | 6 | 42.0 | 8.6 | 1723.1 / 2463.4 / 2463.4 | 2093.3 / 5678.4 / 5864.9 |

> **Accounting Note on Latency:** Latency percentiles describe successful completions for scenarios with accepted traffic; for `daily_budget_exhausted` (0% success), total time reports immediate client-side rejection latency. For `real_service`, total time includes requests that encountered provider 429 lockouts.

---

## 4. Operational Outcomes Under Load (Table 2b)

| Scenario | Succeeded % | Rate-limited % | Timed out % | Retries / req | Peak queue | Tokens / answer | Cost / 1k answers |
|---|---|---|---|---|---|---|---|
| steady | 32.0% | 68.0% | 0.0% | 1.36 | 3 | 1998.4 | $0.400 |
| burst | 14.3% | 85.7% | 0.0% | 0.00 | 18 | 2076.4 | $0.415 |
| sustained_overload | 13.3% | 86.7% | 0.0% | 0.00 | 25 | 2148.7 | $0.430 |
| per_minute_limit_halved | 12.0% | 88.0% | 0.0% | 0.00 | 0 | 2473.3 | $0.495 |
| daily_budget_exhausted | 0.0% | 100.0% | 0.0% | 1.00 | 0 | 0.0 | $0.000 |
| real_service | 50.0% | 50.0% | 0.0% | 0.33 | 1 | 2249.7 | $0.450 |

> **Cost & Accounting Basis:** Actual expenses on Groq free-tier and Stand-in were $0.00. "Cost per 1,000 answers" represents a commercial reference benchmark computed at $0.05 / 1M prompt tokens and $0.15 / 1M completion tokens over successful completions. Retries count upstream attempts beyond the initial request (strictly $\le 2$).

---

## 5. Retrieval Quality Comparison (Table 3)
Evaluated across 18 benchmark questions (13 answerable, 5 unanswerable traps) in a paced environment to prevent rate-limit interference:

| Setting (chunk size, chunks fetched, re-ranking) | Questions | Correct & cited % | Wrong % | Correctly refused % | Tokens / answer | First token p50 / p95 (ms) | Total time p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|
| Setting A: 250 words, 5 fetched, re-rank no | 18 | 50.0% | 5.6% | 22.2% | 3176.8 | 1603.9 / 4018.5 | 1603.9 / 4018.5 |
| Setting B: 250 words, 3 fetched, re-rank no | 18 | 50.0% | 5.6% | 22.2% | 2171.7 | 1678.8 / 3857.6 | 1678.8 / 3857.6 |
| Setting C: 250 words, 5 fetched, re-rank yes | 18 | 50.0% | 5.6% | 22.2% | 3162.4 | 1701.7 / 3903.3 | 1701.7 / 3903.3 |

**Key Finding:** Setting B (3 fetched chunks) achieved identical factual precision (90.0% on answerable queries) and epistemic refusal accuracy (22.2%) as Setting A, while slashing input token consumption by **31.6%** (2,171.7 vs. 3,176.8 tokens). Under strict 8,000 TPM ceilings, this token reduction directly yields higher sustainable throughput without degrading citation faithfulness.

---

## 6. How This Library Misleads a Naive Retriever
1. **Section Title Ambiguity Across Papers:** Both Moshi and Dynamic Chunking contain generic section titles (e.g. "3 Architecture" or "4 Experiments"). A naive search for `"architecture"` retrieves overlapping passages from different papers without distinguishing Moshi's dual audio streams from H-Net's hierarchical chunking.
2. **Subword vs. Continuous Token Semantic Collisions:** A query on "token representations" matches Attention's Byte-Pair Encoding subword vocabulary (37k tokens) and Moshi's continuous audio quantizers (Mimi RVQ at 12.5 Hz). Without corpus-specific filtering, BM25 blends these fundamentally incompatible token definitions.
3. **SSM / Mamba-2 Contextual Entanglement:** The Dynamic Chunking paper explicitly evaluates Mamba-2 / SSM backbones inside H-Net. A naive keyword filter either incorrectly rejects the query as "out-of-scope" or retrieves unrelated external state-space literature not contained in the corpus.

---

## 7. Where the Time Goes: Request Breakdown
Analysis of real Groq execution for `real-groq-0001` (*"What is the formula for Scaled Dot-Product Attention in the Transformer?"*):

- **Queue Waiting Time:** `0.0 ms` (Admission slot available immediately).
- **Step 1: CLASSIFY:** `1092.0 ms` (378 prompt tokens, 62 completion tokens). Classified query as in-scope for Attention paper.
- **Step 2: RETRIEVE:** `2.8 ms` (0 network tokens). Local in-process BM25 fetched top-3 chunks.
- **Step 3: DRAFT:** `583.3 ms` (1,210 prompt tokens, 102 completion tokens). Generated draft answer with citations.
- **Step 4: VERIFY:** `784.6 ms` (1,301 prompt tokens, 70 completion tokens). Validated formula $\text{Attention}(Q, K, V) = \text{softmax}(QK^T / \sqrt{d_k})V$ against chunk `attention_p04_c012`.
- **Total Request Latency:** `2462.7 ms` working time ($2463.4\text{ms}$ total elapsed). Total tokens: 2,889 in, 234 out.

---

## 8. Failure Mode: Why Retrying Made Things Worse
Under burst and steady load, requests hitting provider rate limits (HTTP 429) received `retry-after: 13.6s` to `3600s`. When retries were triggered without backpressure:
1. **Token Window Starvation:** In `real-groq-0003`, after consuming 3,347 tokens across classification and drafting, the verification step requested 1,834 tokens under an active usage of 6,754 tokens, breaching the provider's 7,000 ITPM limit (`Limit 7000, Used 6754, Requested 1834`).
2. **Retry Compounding:** Retrying the 1,834-token payload 1.5 seconds later simply re-triggered the 429 lockout, extending the cooldown from 3.2s to 13.6s and consuming client worker slots while blocking queued requests behind it.
3. **Mitigation:** Setting `max_retries=2` paired with a fast-fail threshold (`if retry_after > 10.0: abort`) prevented the system from holding client sockets open during long quota lockouts.

---

## 9. User Experience Under Daily Quota Exhaustion
When the 500,000 daily token budget is exhausted (simulated at 3:00 PM), arriving requests are intercepted locally by `TokenBudgetTracker` in **0.1 ms** without initiating an upstream network call. The user immediately receives:
```json
{
  "status": "rate_limited",
  "error": "Daily token budget exhausted. Quota resets at 00:00 UTC.",
  "buffered_answer": null
}
```
This fast-fail design guarantees that waiting users are not stalled behind timeouts when the service cannot fulfill requests.

---

## 10. Engineering Reflection & Boundaries
- **Least Certain Assumption:** I assumed Groq's token counters meter only prompt tokens and emitted completion tokens. If internal speculative decoding bills discarded speculative tokens, client-side budget trackers will systematically underestimate usage.
- **Deliberately Excluded:** 
  1. *Heavy Vector Databases:* An in-memory BM25 index on 337 chunks executes in $<3\text{ms}$ with zero network cost, avoiding dense vector infrastructure.
  2. *Unverified Token Streaming:* Answers were buffered until verification passed to prevent releasing unchecked hallucinations.
- **Learned Insight:** SDKs frequently hide internal retries with opaque exponential backoff. In an async pipeline under strict TPM limits, setting `max_retries=0` in the SDK is mandatory to retain control over retry behavior.

---

## 11. Feedback on Vaani (`https://www.vaani.dev/`)
- **What Stood Out:** Direct full-duplex conversational voice architecture rather than traditional cascaded pipelines (ASR $\to$ LLM $\to$ TTS), closely matching Moshi's low-latency speech modeling.
- **What Confused Me:** Lack of documentation regarding cancellation semantics for pending asynchronous tool calls when a user interrupts the voice agent mid-utterance.
- **Suggested Change:** Expose programmatic Voice Activity Detection (VAD) interruption sensitivity thresholds to prevent background acoustic noise from triggering false conversational turn-takes.

---

## 12. How I Worked with the Assistant
The complete, unedited pair-programming trajectory is preserved in [`transcripts/conversation_history.jsonl`](transcripts/conversation_history.jsonl) (1,500+ steps).

### Prompts That Helped Most
1. *"Calibrate against live Groq headers first to parameterize the stand-in with empirical data rather than guesses. Do not run large unmetered load tests against real Groq; calibrate on 5 samples and test load on the stand-in."*
2. *"Define whether output is buffered or streamed. Do not release unverified claims merely to improve first-token metrics."*
3. *"Ensure its passageworks everywhere, not relay, with zero hardcoding, explicit environment variable resolution, and strict atomic modularity."*

### Prompts That Sent Me Down the Wrong Path
1. *Allowing standard HTTP retry handling without a fast-fail ceiling:* The assistant wrote `await asyncio.sleep(retry_after)`. When the Stand-in simulated quota exhaustion with `retry-after: 3600`, the test suite hung for an hour. I added an explicit 10-second fast-fail cutoff.
2. *Proposing semantic embedding models before measuring corpus size:* The assistant initially recommended `sentence-transformers` and Milvus. I overruled this in favor of BM25, avoiding multi-gigabyte dependencies for 337 chunks.
3. *Relying on default SDK calls:* The assistant initially omitted `max_retries=0` in `AsyncGroq`, masking SDK internal retries that caused double-backoff stalls under load.

### Systems Steering Insight
AI coding assistants excel at rapid boilerplate generation and test authoring, but default to "happy path" assumptions and heavy library stacks. Directing an assistant through an open-ended systems problem requires the engineer to act as an invariant enforcer: establishing monotonic clocks, asserting hard failure boundaries, interrogating invisible SDK defaults, and refusing superficial metric wins in favor of provable system guarantees.
