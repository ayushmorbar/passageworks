# 1. What I built and why

Passageworks is an asynchronous question-answering pipeline grounded strictly in three arXiv papers: *Attention Is All You Need* (arXiv:1706.03762v7), *Moshi* (arXiv:2410.00037v1), and *Dynamic Chunking* (arXiv:2507.07955v2). It evaluates system behavior under bursty traffic, provider quotas, and service failures.

The pipeline executes four discrete stages: `CLASSIFY` (zero-cost prompt routing to filter out-of-scope queries or identify target papers), `RETRIEVE` (in-memory BM25 chunk search), `DRAFT` (initial synthesis with explicit citations), and `VERIFY` (independent LLM audit of claim-passage alignment).

The single architectural decision that shaped the system most was buffered verification: withholding all output until an independent LLM validation step confirms exact claim-passage alignment against source citations `[Paper, Section, Page]`. The pipeline buffers output until verification passes. This prevents the release of unverified drafts, but does not guarantee factual correctness.

---

# 2. The real service and my stand-in

To parameterize the pipeline, I probed the live Groq API (`qwen/qwen3.8-27b`) on November 9, 2026, using HTTP response headers and empirical test calls.

### Table 1: Limits

| Limit | Value found | How found | Confidence |
|---|---|---|---|
| Requests per minute | 30 RPM | Groq developer docs; confirmed when burst tests exceeding 30 RPM tripped 429 lockouts | Medium |
| Tokens per minute | 7,000–8,000 ITPM | Header `x-ratelimit-limit-tokens: 8000`; 429 payload cites `Limit 7000 ITPM` | High |
| Requests per day | 1,000 RPD | Header `x-ratelimit-limit-requests: 1000` | High |
| Tokens per day | 500,000 TPD | Groq developer documentation free-tier quota | High |
| Requests in flight at once | ~3–5 concurrent | Inferred provider ceiling; client semaphore set to 4 based on latency inflation above 4 concurrent requests | Medium |
| What it returns when a limit is hit | HTTP 429 JSON | Header `retry-after: Xs` and payload `{"error": {"message": "...", "type": "tokens", "code": "rate_limit_exceeded"}}` | High |
| Time until it recovers | 210ms–13.6s (RPM/TPM); up to 24h (RPD) | Observed reset headers across 6 real probes (`x-ratelimit-reset-tokens`) and 429 `try again in Xs` | Medium |

### Stand-in Design and Calibration
The Stand-in is a local FastAPI service (`passageworks_standin`) mimicking Groq's `/v1/chat/completions`:
- **Calibration Procedure:** Calibrated from 5 controlled baseline probes against live Groq endpoints (`qwen/qwen3.8-27b`) measuring TTFT (median $178.5\text{ ms}$), streaming token cadence ($\sim 65$ tokens/sec via SSE), concurrency degradation, and exact HTTP response header semantics.
- **A Number We Could Not Have Guessed:** Groq's sub-second token replenishment slice interval: the `x-ratelimit-reset-tokens` header reported fractional credit reset times between $210\text{ ms}$ and $630\text{ ms}$ rather than whole-second discrete buckets, while 429 error payloads disclosed exact token balances down to single tokens (`Limit 7000, Used 6754, Requested 1834. Please try again in 13.611428571s`).
- **Load-Dependent Slowdown:** Employs an active-concurrency multiplier: each concurrent request beyond 4 adds $12\%$ latency jitter, reproducing LPU memory bus and queue contention.
- **Differences from Real Service:** The Stand-in emits deterministic text rather than executing full LLM inference, cannot simulate GPU memory bandwidth contention or hardware cache misses, and replenishes token buckets on discrete tick intervals rather than continuous streaming.

---

# 3. Results

### Table 2a: Latency, one row per load scenario

| Scenario | Real or stand-in | Requests sent | Duration (s) | Offered rate (per min) | First token p50 / p95 / p99 (ms) | Total time p50 / p95 / p99 (ms) |
|---|---|---|---|---|---|---|
| steady | stand-in | 25 | 24.1 | 62.3 | 1637.7 / 1931.0 / 2015.1 | 10257.7 / 20458.7 / 21434.3 |
| burst | stand-in | 35 | 14.2 | 147.8 | 1527.3 / 1714.2 / 1725.9 | 0.1 / 1565.8 / 1703.9 |
| sustained_overload | stand-in | 45 | 14.7 | 183.9 | 1798.0 / 2302.8 / 2341.5 | 0.1 / 1814.1 / 2266.1 |
| per_minute_limit_halved | stand-in | 25 | 14.4 | 104.0 | 1603.4 / 1615.9 / 1617.0 | 0.1 / 1602.0 / 1614.0 |
| daily_budget_exhausted | stand-in | 15 | 7.3 | 122.5 | not measured | 7.9 / 378.2 / 1049.4 |
| real_service | real | 6 | 56.2 | 6.4 | 1723.1 / 2389.4 / 2448.6 | 2093.2 / 5795.0 / 5888.3 |

> **Accounting Note on Latency:** Latency percentiles describe successful completions where successes exist (steady, burst, overload, halved limit). For `daily_budget_exhausted`, zero requests succeeded, so percentiles describe all 15 rate-limited rejection latencies. For `real_service`, total-time percentiles describe all six dispatched requests, capturing the impact of provider 429 lockouts.

### Table 2b: Outcomes, same rows

| Scenario | Succeeded % | Rate-limited % | Timed out or given up % | Retries per request | Peak queue length | Tokens per answer | Cost per 1,000 answers |
|---|---|---|---|---|---|---|---|
| steady | 32.0% | 68.0% | 0.0% | 1.36 | 3 | 1998.4 | $0.105 |
| burst | 14.3% | 85.7% | 0.0% | 0.00 | 18 | 2076.4 | $0.109 |
| sustained_overload | 13.3% | 86.7% | 0.0% | 0.00 | 25 | 2148.7 | $0.113 |
| per_minute_limit_halved | 12.0% | 88.0% | 0.0% | 0.00 | 0 | 2473.3 | $0.130 |
| daily_budget_exhausted | 0.0% | 100.0% | 0.0% | 1.00 | 0 | 0.0 | $0.000 |
| real_service | 50.0% | 50.0% | 0.0% | 0.67 | 0 | 2418.3 | $0.138 |

### Who waits, who is dropped, and real-service quality
- **Who waits:** In `steady`, requests queue behind the concurrency limiter (`max_concurrency=4`), waiting up to $20.4\text{ s}$ (p95 total latency $20,458.7\text{ ms}$ vs. $1,931.0\text{ ms}$ TTFT). In `burst`, queued requests wait until the admission queue reaches its cap ($18$), after which newly arriving requests are shed fast ($0.1\text{ ms}$).
- **Who is dropped:** In `sustained_overload` and `burst`, excess requests exceeding capacity or rejected by rate limits are dropped immediately ($0.1\text{ ms}$).
- **Real-Service Quality Breakdown:** Among the six real-service requests in Table 2b, three completed successfully (50.0%): two answered with validated citations (`real-groq-0001`, `0002`) and one correctly refused an out-of-scope question (`real-groq-0005`). The other three were marked `wrong` by the evaluation harness because provider rate limits aborted execution before an answer could be verified (`real-groq-0003` and `0004` hit 429 ITPM exhaustion during revision/verification, while `real-groq-0006` was intercepted at admission at 7,255/8,000 active TPM). No hallucinated answers were delivered; unverified drafts were withheld.

---

# 4. Where the time goes

Analysis of real Groq execution for `real-groq-0001` (*"What is the formula for Scaled Dot-Product Attention in the Transformer?"*):
- **Waiting time:** `0.0 ms` (admission slot immediately available).
- **Working time:** `2,462.7 ms` ($2,463.4\text{ ms}$ total elapsed).
  - `CLASSIFY`: $1,092.0\text{ ms}$ (378 prompt tokens, 62 completion tokens) — routed to Attention paper.
  - `RETRIEVE`: $2.8\text{ ms}$ (0 network tokens) — local in-memory BM25 fetched top-3 chunks.
  - `DRAFT`: $583.3\text{ ms}$ (1,210 prompt tokens, 102 completion tokens) — drafted answer with citations.
  - `VERIFY`: $784.6\text{ ms}$ (1,301 prompt tokens, 70 completion tokens) — audited formula against chunk.
- **Retrying time:** `0.0 ms` (zero retries required).
- **Total tokens:** 2,889 prompt, 234 completion ($3,123$ total).
- **Delay before first token:** Because the system buffers output until verification passes, all $2,463.4\text{ ms}$ is delay before the user sees the first token.

---

# 5. When a limit is hit

When client-side quota monitoring detects that rolling TPM or daily budget is nearly exhausted ($<1,500$ tokens remaining), the pipeline adapts dynamically: it shifts retrieval from 5 chunks to 3 chunks to compress input token load. If insufficient quota remains for a draft-verify cycle, it fast-fails at admission in $<0.1\text{ ms}$ instead of sending doomed upstream requests.

## Retrieval: quality versus cost

### Table 3: Retrieval settings

| Setting (piece size, pieces fetched, re-rank) | Questions asked | Correct and cited % | Wrong % | Correctly refused % | Incorrectly refused % | Tokens per answer | First token p50 / p95 (ms) | Total time p50 / p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| Setting A: 250 words, 5 fetched, re-rank no | 18 | 50.0% | 5.6% | 22.2% | 22.2% | 3176.8 | 1603.9 / 4018.5 | 1603.9 / 4018.5 |
| Setting B: 250 words, 3 fetched, re-rank no | 18 | 50.0% | 5.6% | 22.2% | 22.2% | 2171.7 | 1678.8 / 3857.6 | 1678.8 / 3857.6 |
| Setting C: 250 words, 5 fetched, re-rank yes | 18 | 50.0% | 5.6% | 22.2% | 22.2% | 3162.4 | 1701.7 / 3903.3 | 1701.7 / 3903.3 |

> **Evaluation Disclosure:** Table 3 measures pipeline and retrieval mechanics using the stand-in. It does not establish real-model answer quality across the three retrieval settings. All 60 question-level records are published in [`results/eval_records.csv`](results/eval_records.csv) and [`results/eval_records.jsonl`](results/eval_records.jsonl).

Across the 18 evaluation questions (13 answerable, 5 unanswerable traps):
- **Answerable questions:** 9 of 13 ($69.2\%$) were answered correctly with validated citations. 4 of 13 ($30.8\%$ of answerable; $22.2\%$ of total 18) were incorrectly refused (`refused_wrongly`) because the classifier gatekeeper strictly rejected Dynamic Chunking queries as out of scope.
- **Unanswerable questions:** 4 of 5 ($80.0\%$) were correctly refused (`refused_correctly`), and 1 of 5 ($20.0\%$ of unanswerable; $5.6\%$ of total 18) was wrong (RLHF trap).
- **Token Savings:** Setting B uses 31.6% fewer tokens per attempt ($2,171.7$ vs. $3,176.8$ tokens) while producing the same grade distribution in this 18-question stand-in evaluation. I selected it because it preserves the measured quality pattern while reducing token consumption.

## How this library will mislead a naive retriever
1. **Section Title Ambiguity Across Papers:** Both Moshi and Dynamic Chunking contain generic section titles ("3 Architecture", "4 Experiments"). A naive search for `"architecture"` retrieves overlapping chunks from different papers without isolating Moshi's dual-stream audio from H-Net's sequence chunking.
2. **Subword vs. Continuous Token Semantic Collisions:** A query on "token representations" matches Attention's Byte-Pair Encoding subword vocabulary (37k tokens) and Moshi's continuous audio quantizers (Mimi RVQ at 12.5 Hz). Without corpus-specific filtering, BM25 blends these fundamentally incompatible token definitions.
3. **SSM / Mamba-2 Contextual Entanglement:** The Dynamic Chunking paper explicitly evaluates Mamba-2 / SSM backbones inside H-Net. A naive keyword filter either incorrectly rejects the query as "out-of-scope" or retrieves unrelated external state-space literature not contained in the corpus.

---

# 6. Retries

Under burst and sustained load, retrying requests that hit rate limits frequently made system degradation worse.

In trace `real-groq-0003`, after consuming 3,347 tokens across `CLASSIFY` and `DRAFT`, the `VERIFY` step requested 1,834 tokens against an active usage of 6,754 tokens, returning an HTTP 429 with: `Limit 7000, Used 6754, Requested 1834. Please try again in 13.611428571s`. After a 1.5s client backoff, the retry immediately hit the same 429 condition (`retry-after: 13.6s`). The request therefore consumed $5,911.6\text{ ms}$ across 2 retries without completing. Retrying against a minute-level quota window without waiting for the full lockout period simply compounded latency and held worker slots open.

**Mitigation:** We set `max_retries=2` and added a fast-fail threshold (`if retry_after > 10.0: abort`), immediately aborting retries when provider lockouts exceed 10 seconds.

---

# 7. What the person sees

When the daily token budget (500,000 tokens) is exhausted (simulated at 3:00 PM), arriving requests are halted. The person sees this clear, actionable error message on their screen:
```
Request declined: Daily token budget exhausted. Quota resets at 00:00 UTC.
```
In the benchmark scenario (`daily_budget_exhausted`), 15 requests were dispatched. The first request consumed 1,331 tokens and retried before the budget state was established (taking $1,217.2\text{ ms}$). After the budget was exhausted, subsequent requests were rejected locally in 3.2–18.6 ms (median: $7.9\text{ ms}$, p95: $378.2\text{ ms}$). Waiting users receive an immediate failure response rather than stalling on upstream network timeouts.

---

# 8. What I'm unsure about, what I left out, what I learned

- **What I'm unsure about:** I assumed Groq meters only input prompt tokens and emitted completion tokens. If their LPU speculative decoding engine bills speculative candidate tokens that are subsequently discarded, client-side budget accounting will systematically underestimate actual quota burn.
- **What I left out:**
  1. *Dense Vector Database (Deliberate Scope Choice):* With only 337 chunks across 3 papers, an in-memory BM25 index executes in $<3\text{ ms}$ with zero network overhead. Adding Milvus or pgvector would introduce operational fragility without improving retrieval accuracy.
  2. *Unverified Token Streaming (Deliberate Scope Choice):* Streaming tokens before verification saves perceived TTFT, but risks exposing hallucinations that later fail verification. I left out early streaming to enforce strict epistemic guarantees.
  3. *Multimodal Audio Processing (System Limitation):* The pipeline operates purely on extracted text representations, omitting live speech codec execution.
- **What I learned:** Default SDK configurations are deceptive under load. `AsyncGroq` defaults to internal retries with exponential backoff that hide provider rate limits from client control, causing silent stalling. Setting `max_retries=0` in the SDK and managing backpressure explicitly is essential for predictable pipeline behavior.

---

# 9. Your feedback on Vaani

- **What stood out:** Vaani's direct full-duplex conversational voice architecture (`https://www.vaani.dev/`) bypasses traditional cascaded pipelines (ASR $\to$ LLM $\to$ TTS), mirroring Moshi's continuous real-time audio design.
- **What confused me:** The documentation is unclear about cancellation semantics for pending asynchronous tool calls when a user barges in mid-utterance.
- **One change I would make:** Expose configurable Voice Activity Detection (VAD) sensitivity parameters to prevent ambient room noise from inadvertently interrupting assistant responses.

---

# 10. How I worked with the assistant

The complete, unedited conversation trajectory is archived in [`transcripts/conversation_history.jsonl`](transcripts/conversation_history.jsonl) (1,800+ interaction steps).

### Three prompts that helped most
1. *"Calibrate against live Groq headers first to parameterize the stand-in with empirical data rather than guesses. Do not run large unmetered load tests against real Groq; calibrate on 5 samples and test load on the stand-in."* — Forced empirical grounding and protected limited API quotas.
2. *"Define whether output is buffered or streamed. Do not release unverified claims merely to improve first-token metrics."* — Established the foundational architectural principle of epistemic integrity over cosmetic latency.
3. *"Ensure its passageworks everywhere, not relay, with zero hardcoding, explicit environment variable resolution, and strict atomic modularity."* — Maintained project identity and production-grade configuration cleanliness.

### Three prompts that sent me down the wrong path and how I recovered
1. *Assistant wrote unbounded retry sleeps (`await asyncio.sleep(retry_after)`):* When the Stand-in returned a 1-hour quota lockout (`retry-after: 3600`), tests froze. Ayush intervened to impose a strict 10-second fast-fail cutoff.
2. *Assistant proposed dense embeddings and vector databases:* Over-engineered solution for 337 chunks. Ayush directed it back to deterministic in-memory BM25 with title-filtered routing.
3. *Assistant relied on default SDK client calls:* Masked internal retries that caused double backoff stalls. Ayush enforced explicit `max_retries=0` on the underlying SDK client.

### Steering insight and distinct authorship
AI coding assistants naturally gravitate toward happy paths, generic code snippets, and heavy third-party libraries. Guiding an assistant on systems engineering requires the engineer to act as an invariant enforcer: asserting hard time budgets, designing for failure states, and verifying empirical evidence. What is distinctly Ayush's is the architectural insistence on buffered verification, the sliding-window client token budget tracker with fast-fail lockout, and the title-disambiguated in-memory BM25 index that operates with zero external service dependencies.
