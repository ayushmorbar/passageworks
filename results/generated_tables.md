# Generated Report Tables

### Table 2a: Latency, one row per load scenario

| Scenario                | Real or stand-in | Requests sent | Duration (s) | Offered rate (per min) | First token p50 / p95 / p99 (ms) | Total time p50 / p95 / p99 (ms) |
|-------------------------|------------------|---------------|--------------|------------------------|----------------------------------|---------------------------------|
| steady                  | stand-in         | 25            | 24.1         | 62.3                   | 1637.7 / 1931.0 / 2015.1         | 1637.7 / 1931.0 / 2015.1        |
| burst                   | stand-in         | 35            | 14.2         | 147.8                  | 1527.3 / 1714.2 / 1725.9         | 1527.3 / 1714.2 / 1725.9        |
| sustained_overload      | stand-in         | 45            | 14.7         | 183.9                  | 1798.0 / 2302.8 / 2341.5         | 1798.0 / 2302.8 / 2341.5        |
| per_minute_limit_halved | stand-in         | 25            | 14.4         | 104.0                  | 1603.4 / 1615.9 / 1617.0         | 1603.4 / 1615.9 / 1617.0        |
| daily_budget_exhausted  | stand-in         | 15            | 7.3          | 122.5                  | not measured                     | 7.9 / 378.2 / 1049.4            |

### Table 2b: Outcomes, same rows

| Scenario                | Succeeded % | Rate-limited % | Timed out or given up % | Retries per request | Peak queue length | Tokens per answer | Cost per 1,000 answers |
|-------------------------|-------------|----------------|-------------------------|---------------------|-------------------|-------------------|------------------------|
| steady                  | 32.0%       | 68.0%          | 0.0%                    | 1.36                | 3                 | 1998.4            | $0.400                 |
| burst                   | 14.3%       | 85.7%          | 0.0%                    | 0.0                 | 18                | 2076.4            | $0.415                 |
| sustained_overload      | 13.3%       | 86.7%          | 0.0%                    | 0.0                 | 25                | 2148.7            | $0.430                 |
| per_minute_limit_halved | 12.0%       | 88.0%          | 0.0%                    | 0.0                 | 0                 | 2473.3            | $0.495                 |
| daily_budget_exhausted  | 0.0%        | 100.0%         | 0.0%                    | 1.0                 | 0                 | 0.0               | $0.000                 |

### Table 3: Retrieval settings

| Setting (piece size, pieces fetched, re-rank) | Questions asked | Correct and cited % | Wrong % | Correctly refused % | Tokens per answer | First token p50 / p95 (ms) | Total time p50 / p95 (ms) |
|-----------------------------------------------|-----------------|---------------------|---------|---------------------|-------------------|----------------------------|---------------------------|
| Setting A: 250 words, 5 fetched, re-rank no   | 18              | 50.0%               | 5.6%    | 22.2%               | 3176.8            | 1603.9 / 4018.5            | 1603.9 / 4018.5           |
| Setting B: 250 words, 3 fetched, re-rank no   | 18              | 50.0%               | 5.6%    | 22.2%               | 2171.7            | 1678.8 / 3857.6            | 1678.8 / 3857.6           |
| Setting C: 250 words, 5 fetched, re-rank yes  | 18              | 50.0%               | 5.6%    | 22.2%               | 3162.4            | 1701.7 / 3903.3            | 1701.7 / 3903.3           |
