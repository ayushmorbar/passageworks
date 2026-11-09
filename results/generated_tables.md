# Generated Report Tables

### Table 2a: Latency, one row per load scenario

| Scenario                | Real or stand-in | Requests sent | Duration (s) | Offered rate (per min) | First token p50 / p95 / p99 (ms) | Total time p50 / p95 / p99 (ms) |
|-------------------------|------------------|---------------|--------------|------------------------|----------------------------------|---------------------------------|
| steady                  | stand-in         | 25            | 24.0         | 62.5                   | 1716.5 / 1776.5 / 1781.5         | 1716.5 / 1776.5 / 1781.5        |
| burst                   | stand-in         | 35            | 14.2         | 148.1                  | 1705.4 / 1913.8 / 1943.2         | 1705.4 / 1913.8 / 1943.2        |
| sustained_overload      | stand-in         | 45            | 14.7         | 183.9                  | 1893.0 / 2455.0 / 2504.1         | 1893.0 / 2455.0 / 2504.1        |
| per_minute_limit_halved | stand-in         | 25            | 14.5         | 103.3                  | 1762.5 / 1826.7 / 1832.4         | 1762.5 / 1826.7 / 1832.4        |
| daily_budget_exhausted  | stand-in         | 15            | 7.4          | 121.4                  | not measured                     | 8.1 / 398.3 / 1121.6            |

### Table 2b: Outcomes, same rows

| Scenario                | Succeeded % | Rate-limited % | Timed out or given up % | Retries per request | Peak queue length | Tokens per answer | Cost per 1,000 answers |
|-------------------------|-------------|----------------|-------------------------|---------------------|-------------------|-------------------|------------------------|
| steady                  | 32.0%       | 68.0%          | 0.0%                    | 2.04                | 3                 | 1980.4            | $0.396                 |
| burst                   | 17.1%       | 82.9%          | 0.0%                    | 0.0                 | 18                | 2130.7            | $0.426                 |
| sustained_overload      | 13.3%       | 86.7%          | 0.0%                    | 0.0                 | 25                | 2130.7            | $0.426                 |
| per_minute_limit_halved | 12.0%       | 88.0%          | 0.0%                    | 0.0                 | 0                 | 2455.3            | $0.491                 |
| daily_budget_exhausted  | 0.0%        | 100.0%         | 0.0%                    | 1.0                 | 0                 | 0.0               | $0.000                 |

### Table 3: Retrieval settings

| Setting (piece size, pieces fetched, re-rank) | Questions asked | Correct and cited % | Wrong % | Correctly refused % | Tokens per answer | First token p50 / p95 (ms) | Total time p50 / p95 (ms) |
|-----------------------------------------------|-----------------|---------------------|---------|---------------------|-------------------|----------------------------|---------------------------|
| 250 words, 5 fetched, re-rank no              | 18              | 33.3%               | 38.9%   | 27.8%               | 1381.7            | 1641.4 / 1757.2            | 1641.4 / 1757.2           |
| 250 words, 3 fetched, re-rank no              | 18              | 33.3%               | 38.9%   | 27.8%               | 975.0             | 1638.8 / 1757.7            | 1638.8 / 1757.7           |
| 250 words, 5 fetched, re-rank yes             | 18              | 33.3%               | 38.9%   | 27.8%               | 1393.9            | 1637.4 / 1831.4            | 1637.4 / 1831.4           |

