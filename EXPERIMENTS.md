# EXPERIMENTS.md — Empirical Evaluation Plan & Run Registry

## 1. Experimental Methodology
- **Clock Source:** Python `time.perf_counter()` (monotonic).
- **Network Mode:** Open-loop load generator (requests dispatched per schedule regardless of prior completions).
- **Metrics Collected:**
  - `start_time` (ISO 8601 UTC)
  - `first_token_ms` (user-visible elapsed time to first answer token)
  - `total_ms` (total pipeline completion time)
  - `status` (`ok`, `rate_limited`, `timeout`, `error`)
  - `retries` (number of retry attempts triggered)
  - `tokens_in`, `tokens_out` (extracted from provider response metadata)
  - `retrieval_setting` (identifier of chunking/retrieval configuration)
  - `answer_grade` (`correct`, `wrong`, `refused_correctly`, `refused_wrongly`)

## 2. Load Scenarios (Mandatory Table 2a & 2b)

| Scenario Name | Traffic Shape | Target Offered Rate | Duration | Primary Test Surface |
|---|---|---|---|---|
| **Steady** | Constant Poisson/uniform arrival | ~10 req/min | 180s | Baseline latency & queue stability |
| **Burst** | Sharp step from 5 req/min to 35 req/min | Spike at t=30s | 120s | Queue absorption, peak backlog |
| **Sustained Overload** | Continuous 40 req/min (> free-tier cap) | 40 req/min | 180s | 429 shedding, backpressure, timeouts |
| **Limit Halved** | Stand-in with RPM cut from 30 to 15 | 15 req/min | 180s | Latency distribution under degraded quota |
| **Daily Exhausted** | Cumulative tokens breach daily ceiling | Continuous | N/A | Immediate rejection, user-facing 3pm UX |

## 3. Retrieval Variations (Mandatory Table 3)
Evaluated on a fixed set of >=15 verified technical questions:
- **Setting A (Fine-grained BM25):** Small chunks (~250 words, 50-word overlap), top-5 passages fetched, no re-ranking.
- **Setting B (Coarse-grained BM25):** Section-level chunks (~600 words), top-3 passages fetched, no re-ranking.
- **Setting C (Hybrid / Filtered BM25):** Section-level chunks, top-5 fetched with lexical title-boosting / re-ranking filter.

## 4. Run Execution Index
*(Populated as experiments execute)*

| Run ID | Timestamp | Scenario | Target Service | Requests Sent | Commit Hash | Output Trace |
|---|---|---|---|---|---|---|
| *TBD* | | | | | | |
