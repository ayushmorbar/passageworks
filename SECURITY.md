# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability within Passageworks, please do not open a public issue. Instead, report it privately to the project maintainer:

- **Maintainer:** Ayush Morbar
- **Email:** Report security issues via GitHub Security Advisories on this repository or directly to the repository owner.

Please include:
1. Description of the vulnerability and potential impact.
2. Minimal steps to reproduce or proof-of-concept script.
3. Suggested fix or remediation if known.

We will acknowledge receipt within 48 hours and provide a remediation timeline.

---

## Credential & Secret Protection Policy

1. **Zero Secret Commits:** API keys (such as `GROQ_API_KEY`) must never be committed to Git. The repository's `.gitignore` explicitly excludes `.env*` files (except the template `.env.example`).
2. **Offline-by-Default CI:** All automated GitHub Actions and local unit/integration tests run without requiring real cloud API credentials. CI tests execute against an in-memory transport or local Stand-in server (`relay_standin`).
3. **Prompt & Evidence Sanitization:** Retrieved paper text is treated strictly as evidence data, never as executable code or administrative instructions.
4. **Rate Limit Defense:** Client-side token budgeting and bounded queue admission protect downstream accounts from runaway loops, quota exhaustion, and denial-of-wallet scenarios.
