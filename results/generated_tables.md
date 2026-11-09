# Generated Report Tables

### Table 2a: Latency, one row per load scenario

| Scenario                | Real or stand-in | Requests sent | Duration (s) | Offered rate (per min) | First token p50 / p95 / p99 (ms) | Total time p50 / p95 / p99 (ms) |
|-------------------------|------------------|---------------|--------------|------------------------|----------------------------------|---------------------------------|
| steady                  | stand-in         | 25            | 23.9         | 62.8                   | 1566.5 / 1854.3 / 1928.1         | 9763.2 / 20354.0 / 20957.5      |
| burst                   | stand-in         | 35            | 12.8         | 163.7                  | 1664.1 / 1830.0 / 1846.0         | 0.1 / 1699.1 / 1822.8           |
| sustained_overload      | stand-in         | 45            | 14.7         | 183.9                  | 1681.3 / 2294.8 / 2363.2         | 0.1 / 1686.9 / 2229.7           |
| per_minute_limit_halved | stand-in         | 25            | 14.4         | 104.4                  | 1676.5 / 1702.9 / 1705.2         | 0.1 / 1673.7 / 1698.8           |
| daily_budget_exhausted  | stand-in         | 15            | 7.6          | 118.9                  | not measured                     | 8.3 / 394.6 / 1112.3            |
| real_service            | real             | 6             | 56.2         | 6.4                    | 1723.1 / 2389.4 / 2448.6         | 2093.2 / 5795.0 / 5888.3        |

### Table 2b: Outcomes, same rows

| Scenario                | Succeeded % | Rate-limited % | Timed out or given up % | Retries per request | Peak queue length | Tokens per answer | Cost per 1,000 answers |
|-------------------------|-------------|----------------|-------------------------|---------------------|-------------------|-------------------|------------------------|
| steady                  | 32.0%       | 68.0%          | 0.0%                    | 1.36                | 3                 | 1998.4            | $0.105                 |
| burst                   | 17.1%       | 82.9%          | 0.0%                    | 0.0                 | 18                | 2148.7            | $0.113                 |
| sustained_overload      | 13.3%       | 86.7%          | 0.0%                    | 0.0                 | 25                | 2148.7            | $0.113                 |
| per_minute_limit_halved | 12.0%       | 88.0%          | 0.0%                    | 0.0                 | 0                 | 2473.3            | $0.130                 |
| daily_budget_exhausted  | 0.0%        | 100.0%         | 0.0%                    | 1.0                 | 0                 | 0.0               | $0.000                 |
| real_service            | 50.0%       | 50.0%          | 0.0%                    | 0.67                | 0                 | 2418.3            | $0.138                 |

### Table 3: Retrieval settings

| Setting (piece size, pieces fetched, re-rank) | Questions asked | Correct and cited % | Wrong % | Correctly refused % | Incorrectly refused % | Tokens per answer | First token p50 / p95 (ms) | Total time p50 / p95 (ms) |
|-----------------------------------------------|-----------------|---------------------|---------|---------------------|-----------------------|-------------------|----------------------------|---------------------------|
| Setting A: 250 words, 5 fetched, re-rank no   | 18              | 50.0%               | 5.6%    | 22.2%               | 22.2%                 | 3176.8            | 1631.1 / 3910.4            | 1631.1 / 3910.4           |
| Setting B: 250 words, 3 fetched, re-rank no   | 18              | 50.0%               | 5.6%    | 22.2%               | 22.2%                 | 2171.7            | 1598.8 / 3932.0            | 1598.8 / 3932.0           |
| Setting C: 250 words, 5 fetched, re-rank yes  | 18              | 50.0%               | 5.6%    | 22.2%               | 22.2%                 | 3162.4            | 1634.0 / 3908.4            | 1634.0 / 3908.4           |
