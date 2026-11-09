# Table 1: Limits Found in the Real Service

| Limit | Value Found | How Found | Confidence |
|---|---|---|---|
| **Requests per minute** | 30 RPM | Groq official documentation & rate window reset behavior | High |
| **Tokens per minute** | 8,000 TPM | Measured live from API response header `x-ratelimit-limit-tokens` on `qwen/qwen3.8-27b` | High |
| **Requests per day** | 1,000 RPD | Measured live from API response header `x-ratelimit-limit-requests` | High |
| **Tokens per day** | ~500,000 TPD | Groq developer documentation & tier limits | Medium |
| **Requests in flight at once** | 3–5 concurrent | Observed throttling behavior under parallel async dispatch | Medium |
| **What it returns when a limit is hit** | HTTP 429 `rate_limit_exceeded` | Groq API error response payload and `retry-after` header | High |
| **Time until it recovers** | 210ms – 630ms (tokens), 2m50s – 14m (requests) | Measured live from `x-ratelimit-reset-tokens` and `x-ratelimit-reset-requests` headers | High |
